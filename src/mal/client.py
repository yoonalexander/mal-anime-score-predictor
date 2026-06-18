from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional

import requests
from pydantic import BaseModel

JIKAN_BASE = "https://api.jikan.moe/v4"
COOLDOWN = float(os.getenv("JIKAN_COOLDOWN", 1.2))


class JikanClient:
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
            wait = self.cooldown * (2 ** attempt)
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

    # Seasons list (historical)
    def season(self, year: int, season: str) -> Dict[str, Any]:
        return self.get(f"seasons/{year}/{season}")

    def season_all(self, year: int, season: str) -> Dict[str, Any]:
        first = self.season(year, season)
        data = list(first.get("data") or [])
        last_page = int((first.get("pagination") or {}).get("last_visible_page") or 1)

        for page in range(2, last_page + 1):
            payload = self.get(f"seasons/{year}/{season}", params={"page": page})
            data.extend(payload.get("data") or [])

        first["data"] = data
        return first

    # Upcoming season list
    def seasons_upcoming(self) -> Dict[str, Any]:
        return self.get("seasons/upcoming")

    # Anime details
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
    relations: list[dict] | None = None
