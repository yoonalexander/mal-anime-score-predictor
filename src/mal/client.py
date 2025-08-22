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

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base}/{path.lstrip('/')}"
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        time.sleep(self.cooldown)
        return r.json()

    # Seasons list (historical)
    def season(self, year: int, season: str) -> Dict[str, Any]:
        return self.get(f"seasons/{year}/{season}")

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