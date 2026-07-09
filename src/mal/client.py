from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional

import requests
from pydantic import BaseModel

JIKAN_BASE = "https://api.jikan.moe/v4"
ANILIST_BASE = "https://graphql.anilist.co"
COOLDOWN = float(os.getenv("JIKAN_COOLDOWN", 1.2))


def pick_image_url(images: Optional[Dict[str, Any]]) -> Optional[str]:
    """Pick the best available image URL from a Jikan-shaped ``images`` object."""
    if not images:
        return None
    webp = images.get("webp") or {}
    jpg = images.get("jpg") or {}
    return (
        webp.get("large_image_url")
        or jpg.get("large_image_url")
        or webp.get("image_url")
        or jpg.get("image_url")
        or None
    )


class JikanClient:
    """Client for Jikan (MyAnimeList) with AniList GraphQL fallback.

    Jikan is preferred (it is the canonical MAL source). When a Jikan season
    request fails (MAL upstream issues, 429/5xx), we transparently fall back to
    AniList, which also exposes cover images and the same core metadata.
    """

    def __init__(self, base: str = JIKAN_BASE, cooldown: float = COOLDOWN):
        self.base = base.rstrip("/")
        self.cooldown = cooldown
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "mal-anime-score-predictor/1.0 (+https://github.com/yoonalexander/mal-anime-score-predictor)"}
        )

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base}/{path.lstrip('/')}"
        last_error: requests.HTTPError | None = None
        for attempt in range(4):
            r = self.session.get(url, params=params, timeout=30)
            if r.status_code not in {429, 500, 502, 503, 504}:
                r.raise_for_status()
                time.sleep(self.cooldown)
                return r.json()

            last_error = requests.HTTPError(f"{r.status_code} Server Error for url: {r.url}", response=r)
            # 504 from Jikan usually means MAL is unreachable upstream; back off harder.
            wait = self.cooldown * (2 ** attempt)
            if r.status_code in {502, 503, 504}:
                wait = max(wait, 5.0 * (attempt + 1))
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = max(wait, float(retry_after))
                except ValueError:
                    pass
            time.sleep(wait)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to fetch {url}")

    # ------------------------------------------------------------------
    # Seasons (historical + upcoming)
    # ------------------------------------------------------------------
    def season(self, year: int, season: str) -> Dict[str, Any]:
        return self.get(f"seasons/{year}/{season}")

    def season_all(self, year: int, season: str) -> Dict[str, Any]:
        """Fetch every page of a Jikan season response."""
        first = self.season(year, season)
        data = list(first.get("data") or [])
        last_page = int((first.get("pagination") or {}).get("last_visible_page") or 1)

        for page in range(2, last_page + 1):
            payload = self.get(f"seasons/{year}/{season}", params={"page": page})
            data.extend(payload.get("data") or [])

        first["data"] = data
        return first

    def anilist_season_all(self, year: int, season: str) -> Dict[str, Any]:
        """Fetch an entire season from AniList, paginated, with cover images."""
        query = """
        query ($seasonYear: Int!, $season: MediaSeason!, $page: Int!) {
          Page(page: $page, perPage: 50) {
            pageInfo {
              hasNextPage
            }
            media(type: ANIME, seasonYear: $seasonYear, season: $season, sort: POPULARITY_DESC) {
              id
              idMal
              title {
                romaji
                english
              }
              format
              episodes
              duration
              source
              description(asHtml: false)
              popularity
              favourites
              averageScore
              meanScore
              status
              season
              seasonYear
              coverImage { extraLarge large medium color }
              studios(isMain: true) { nodes { name } }
              genres
              tags { name rank }
              countryOfOrigin
            }
          }
        }
        """
        variables = {"seasonYear": year, "season": season.upper(), "page": 1}
        data: list[dict[str, Any]] = []

        while True:
            response = self._post_anilist({"query": query, "variables": variables})
            payload = response.json()["data"]["Page"]
            data.extend(self._anilist_to_jikan_item(item, year, season) for item in payload["media"])

            if not payload["pageInfo"]["hasNextPage"]:
                break

            variables["page"] += 1
            time.sleep(max(self.cooldown, 2.0))

        return {"data": data, "pagination": {"source": "anilist"}}

    def _post_anilist(self, body: Dict[str, Any]) -> requests.Response:
        last_error: requests.HTTPError | None = None

        for attempt in range(6):
            response = self.session.post(ANILIST_BASE, json=body, timeout=30)
            if response.status_code != 429:
                response.raise_for_status()
                time.sleep(max(self.cooldown, 2.0))
                return response

            last_error = requests.HTTPError(f"429 Client Error for url: {response.url}", response=response)
            retry_after = response.headers.get("Retry-After")
            wait = 30.0 * (attempt + 1)
            if retry_after:
                try:
                    wait = max(wait, float(retry_after))
                except ValueError:
                    pass
            time.sleep(wait)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to fetch AniList GraphQL response")

    @staticmethod
    def _anilist_to_jikan_item(item: Dict[str, Any], year: int, season: str) -> Dict[str, Any]:
        """Map an AniList media node to a Jikan-shaped item (with images)."""
        title = item.get("title") or {}
        score = item.get("averageScore")
        studios = [{"name": studio.get("name")} for studio in (item.get("studios") or {}).get("nodes", [])]
        genres = [{"name": name} for name in item.get("genres") or []]
        # AniList exposes "tags" which roughly correspond to Jikan "themes".
        tags = item.get("tags") or []
        themes = [{"name": t.get("name")} for t in tags if t.get("name")]

        cover = item.get("coverImage") or {}
        cover_url = cover.get("extraLarge") or cover.get("large") or cover.get("medium")
        # Shape like Jikan's images block so downstream code is source-agnostic.
        images = (
            {"jpg": {"large_image_url": cover_url}, "webp": {"large_image_url": cover_url}}
            if cover_url
            else None
        )

        return {
            "mal_id": item.get("idMal") or item.get("id"),
            "title": title.get("english") or title.get("romaji"),
            "type": item.get("format"),
            "episodes": item.get("episodes"),
            "duration": str(item.get("duration")) if item.get("duration") else None,
            "source": item.get("source"),
            "rating": None,
            "year": item.get("seasonYear") or year,
            "season": (item.get("season") or season).lower(),
            "synopsis": item.get("description"),
            "members": item.get("popularity"),
            "favorites": item.get("favourites"),
            "score": score / 10 if score is not None else None,
            "status": item.get("status"),
            "studios": studios,
            "demographics": [],
            "genres": genres,
            "themes": themes,
            "relations": [],
            "images": images,
            "image_url": cover_url,
        }

    # ------------------------------------------------------------------
    # Upcoming season list
    # ------------------------------------------------------------------
    def seasons_upcoming(self) -> Dict[str, Any]:
        return self.get("seasons/upcoming")

    def anilist_upcoming(self) -> Dict[str, Any]:
        """Best-effort AniList fallback for the 'upcoming' schedule.

        AniList has no single 'upcoming' endpoint, so we query the next two
        calendar seasons and let the caller normalize them.
        """
        from datetime import datetime

        SEASONS = ["winter", "spring", "summer", "fall"]
        now = datetime.utcnow()
        idx = (now.month - 1) // 3  # 0..3
        s1 = SEASONS[idx]
        y1 = now.year
        s2 = SEASONS[(idx + 1) % 4]
        y2 = y1 + (1 if (idx + 1) >= 4 else 0)

        data: list[dict[str, Any]] = []
        for y, s in [(y1, s1), (y2, s2)]:
            try:
                payload = self.anilist_season_all(y, s)
                data.extend(payload.get("data") or [])
            except Exception:
                continue
        # Dedup by mal_id
        seen = set()
        unique = []
        for d in data:
            mid = d.get("mal_id")
            if mid is None or mid in seen:
                continue
            seen.add(mid)
            unique.append(d)
        return {"data": unique, "pagination": {"source": "anilist"}}

    # ------------------------------------------------------------------
    # Anime details (used for label backfill)
    # ------------------------------------------------------------------
    def anime(self, mal_id: int) -> Dict[str, Any]:
        return self.get(f"anime/{mal_id}/full")


# Simple pydantic models (subset) for validation/normalization
class AnimeItem(BaseModel):
    mal_id: int
    title: str | None = None
    type: str | None = None
    episodes: int | None = None
    duration: str | None = None
    source: str | None = None
    rating: str | None = None
    year: int | None = None
    season: str | None = None
    synopsis: str | None = None
    members: int | None = None
    favorites: int | None = None
    score: float | None = None
    status: str | None = None
    studios: list[dict] | None = None
    demographics: list[dict] | None = None
    genres: list[dict] | None = None
    themes: list[dict] | None = None
    relations: list[dict] | None = None
    images: dict | None = None
    image_url: str | None = None
