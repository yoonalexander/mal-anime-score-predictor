from __future__ import annotations
import argparse
import os
from typing import Iterable, List

import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint

from .mal.client import JikanClient
from .utils.io import RAW, NORMALIZED, save_json

SEASONS = ["winter", "spring", "summer", "fall"]


def season_iter(start_year: int, end_year: int, seasons: Iterable[str]) -> Iterable[tuple[int, str]]:
    for y in range(start_year, end_year + 1):
        for s in seasons:
            yield y, s


def normalize_season_payload(payload: dict, year: int | None, season: str) -> pd.DataFrame:
    """
    Normalize a Jikan seasons payload (or upcoming) to a compact table.
    """
    data = payload.get("data", []) or []
    rows = []
    for item in data:
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


def _append_to_normalized(df_new: pd.DataFrame) -> pd.DataFrame:
    """
    Append df_new to data/normalized/anime.parquet, align columns, drop dups by mal_id.
    Returns the merged DataFrame.
    """
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    out = NORMALIZED / "anime.parquet"

    if not out.exists():
        merged = df_new.reset_index(drop=True)
        merged.to_parquet(out, index=False)
        return merged

    base = pd.read_parquet(out)

    # Fast paths for empties
    if base.empty and df_new.empty:
        return base
    if base.empty:
        merged = df_new.reset_index(drop=True)
        merged.to_parquet(out, index=False)
        return merged
    if df_new.empty:
        return base

    # Align columns (union), then concat
    all_cols = list(set(base.columns) | set(df_new.columns))
    base_aligned = base.reindex(columns=all_cols)
    new_aligned = df_new.reindex(columns=all_cols)

    merged = (
        pd.concat([base_aligned, new_aligned], ignore_index=True)
        .drop_duplicates("mal_id", keep="last")
        .reset_index(drop=True)
    )
    merged.to_parquet(out, index=False)
    return merged


def ingest_upcoming():
    """
    Ingest MAL's 'upcoming' list and append it to anime.parquet.
    """
    load_dotenv()
    client = JikanClient()

    rprint("[cyan]Fetching upcoming...[/cyan]")
    payload = client.seasons_upcoming()

    # Save raw
    season_dir = RAW / "upcoming"
    season_dir.mkdir(parents=True, exist_ok=True)
    save_json(payload, season_dir / "upcoming.json")

    # Normalize and append
    df = normalize_season_payload(payload, year=None, season="upcoming")
    df["season_key"] = "upcoming"
    merged = _append_to_normalized(df)

    rprint(f"[green]Appended {len(df)} upcoming rows -> {NORMALIZED / 'anime.parquet'} (total {len(merged)})[/green]")


def run_ingest(start_year: int, end_year: int, seasons: List[str]):
    """
    Ingest seasons in the given range and append to anime.parquet (no overwrite).
    """
    load_dotenv()
    client = JikanClient()
    all_dfs: list[pd.DataFrame] = []

    for year, season in season_iter(start_year, end_year, seasons):
        rprint(f"[cyan]Fetching {year} {season}...[/cyan]")
        season_dir = RAW / f"{year}_{season}"
        season_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = client.season_all(year, season)  # all pages w/ retries
            save_json(payload, season_dir / "season.json")
            df = normalize_season_payload(payload, year, season)
            df["season_key"] = df["year"].astype(str) + "_" + df["season"].astype(str)
            all_dfs.append(df)
        except Exception as e:
            rprint(f"[red]Failed {year} {season}: {e}[/red]")
            # keep going

    if not all_dfs:
        rprint("[yellow]No data ingested. Check network or try a smaller range first.[/yellow]")
        return

    # Append to normalized store (dedup by mal_id)
    full = pd.concat(all_dfs, ignore_index=True)
    merged = _append_to_normalized(full)
    rprint(f"[green]Wrote {len(merged)} rows -> {NORMALIZED / 'anime.parquet'}[/green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=False)
    parser.add_argument("--end-year", type=int, required=False)
    parser.add_argument(
        "--seasons",
        nargs="*",
        default=os.getenv("DEFAULT_SEASONS", "winter,spring,summer,fall").split(","),
        help="Seasons to ingest (default: winter spring summer fall)",
    )
    parser.add_argument("--upcoming", action="store_true", help="Ingest upcoming season list")
    args = parser.parse_args()

    if args.upcoming:
        ingest_upcoming()
    else:
        if args.start_year is None or args.end_year is None:
            raise SystemExit("When not using --upcoming, you must pass --start-year and --end-year.")
        run_ingest(args.start_year, args.end_year, [s.lower() for s in args.seasons])
