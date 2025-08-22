from __future__ import annotations
import argparse
import itertools
import os
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint

from .mal.client import JikanClient, AnimeItem
from .utils.io import RAW, NORMALIZED, save_json

SEASONS = ["winter", "spring", "summer", "fall"]


def season_iter(start_year: int, end_year: int, seasons: Iterable[str]) -> Iterable[tuple[int, str]]:
    for y in range(start_year, end_year + 1):
        for s in seasons:
            yield y, s


def normalize_season_payload(payload: dict, year: int, season: str) -> pd.DataFrame:
    data = payload.get("data", [])
    rows = []
    for item in data:
        # Jikan returns nested; select a subset
        row = {
            "mal_id": item.get("mal_id"),
            "title": item.get("title"),
            "type": item.get("type"),
            "episodes": item.get("episodes"),
            "duration": item.get("duration"),
            "source": item.get("source"),
            "rating": item.get("rating"),
            "year": year,
            "season": season,
            "synopsis": item.get("synopsis"),
            "members": item.get("members"),
            "favorites": item.get("favorites"),
            "score": item.get("score"),
            "status": item.get("status"),
            "studios": item.get("studios"),
            "demographics": item.get("demographics"),
            "genres": item.get("genres"),
            "relations": item.get("relations"),
        }
        rows.append(row)
    df = pd.DataFrame(rows).drop_duplicates("mal_id")
    return df


def run_ingest(start_year: int, end_year: int, seasons: List[str]):
    load_dotenv()
    client = JikanClient()
    all_dfs = []

    for year, season in season_iter(start_year, end_year, seasons):
        rprint(f"[cyan]Fetching {year} {season}...[/cyan]")
        payload = client.season(year, season)

        # Save raw
        season_dir = RAW / f"{year}_{season}"
        season_dir.mkdir(parents=True, exist_ok=True)
        save_json(payload, season_dir / "season.json")

        # Normalize
        df = normalize_season_payload(payload, year, season)
        df["season_key"] = df["year"].astype(str) + "_" + df["season"].astype(str)
        all_dfs.append(df)

    full = pd.concat(all_dfs, ignore_index=True)
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    out = NORMALIZED / "anime.parquet"
    full.to_parquet(out, index=False)
    rprint(f"[green]Wrote {len(full)} rows -> {out}[/green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--seasons", nargs="*", default=os.getenv("DEFAULT_SEASONS", "winter,spring,summer,fall").split(","))
    args = parser.parse_args()
    run_ingest(args.start_year, args.end_year, [s.lower() for s in args.seasons])