from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint

from .mal.client import JikanClient, pick_image_url
from .utils.io import RAW, NORMALIZED, save_json, load_json

SEASONS = ["winter", "spring", "summer", "fall"]


def season_iter(start_year: int, end_year: int, seasons: Iterable[str]) -> Iterable[tuple[int, str]]:
    for y in range(start_year, end_year + 1):
        for s in seasons:
            yield y, s


def _extract_name_list(items):
    """Turn a list of {'name': ...} dicts (or plain strings/arrays) into a list of names.

    Robust to NaN scalars, numpy arrays, nested lists, and dicts as produced by
    different API sources and parquet round-trips.
    """
    # NaN / None / empty
    if items is None:
        return []
    try:
        if isinstance(items, float) and np.isnan(items):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(items, str):
        return [items] if items else []
    if isinstance(items, dict):
        n = items.get("name")
        return [str(n)] if n else []

    # Iterable (list, tuple, numpy array).
    out = []
    for it in items:
        if isinstance(it, dict):
            n = it.get("name")
            if n:
                out.append(str(n))
        elif isinstance(it, str) and it:
            out.append(it)
        elif isinstance(it, (list, tuple)):
            out.extend(_extract_name_list(it))
    return out


def normalize_season_payload(payload: dict, year: int | None, season: str) -> pd.DataFrame:
    """
    Normalize a Jikan/AniList seasons payload (or upcoming) to a compact table.

    Captures image URLs and richer metadata (themes, demographics) so the
    frontend can render covers without extra API calls.
    """
    data = payload.get("data", []) or []
    rows = []
    for item in data:
        images = item.get("images")
        image_url = item.get("image_url") or pick_image_url(images)
        # Determine the most accurate year/season from the item itself, falling
        # back to the requested values (upcoming payloads lack them).
        aired = item.get("aired") or {}
        aired_from = aired.get("from") if isinstance(aired, dict) else None
        item_year = item.get("year")
        if item_year is None and aired_from:
            try:
                item_year = int(aired_from[:4])
            except (ValueError, TypeError):
                item_year = year
        if item_year is None:
            item_year = year
        item_season = (item.get("season") or season)

        row = {
            "mal_id": item.get("mal_id"),
            "title": item.get("title"),
            "type": item.get("type"),
            "episodes": item.get("episodes"),
            "duration": item.get("duration"),
            "source": item.get("source"),
            "rating": item.get("rating"),
            "year": item_year,
            "season": item_season,
            "synopsis": item.get("synopsis"),
            "members": item.get("members"),
            "favorites": item.get("favorites"),
            "score": item.get("score"),
            "status": item.get("status"),
            "studios": _extract_name_list(item.get("studios")),
            "demographics": _extract_name_list(item.get("demographics")),
            "genres": _extract_name_list(item.get("genres")),
            "themes": _extract_name_list(item.get("themes")),
            "relations": item.get("relations"),
            "images": images,
            "image_url": image_url,
        }
        rows.append(row)
    df = pd.DataFrame(rows).drop_duplicates("mal_id")
    return df


LIST_COLS = ("studios", "demographics", "genres", "themes")


def _canonicalize_list_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce list columns to a consistent list-of-strings type.

    The historical store may hold list-of-dicts (old AniList mapping) while new
    ingests produce list-of-strings. pyarrow cannot write a column that mixes
    struct arrays and string arrays, so we normalize everything to strings.
    """
    for col in LIST_COLS:
        if col in df.columns:
            df[col] = df[col].apply(lambda cell: _extract_name_list(cell))
        else:
            df[col] = [[] for _ in range(len(df))]
    return df


def _append_to_normalized(df_new: pd.DataFrame) -> pd.DataFrame:
    """
    Append df_new to data/normalized/anime.parquet, align columns, drop dups by mal_id.
    Returns the merged DataFrame.
    """
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    out = NORMALIZED / "anime.parquet"

    df_new = _canonicalize_list_cols(df_new)

    if not out.exists():
        merged = df_new.reset_index(drop=True)
        merged.to_parquet(out, index=False)
        return merged

    base = _canonicalize_list_cols(pd.read_parquet(out))

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


def fetch_season_payload(
    client: JikanClient, year: int, season: str, source: str
) -> tuple[dict, str]:
    if source == "anilist":
        return client.anilist_season_all(year, season), "anilist"

    if source == "jikan":
        return client.season_all(year, season), "jikan"

    # auto: Jikan first, AniList fallback
    try:
        return client.season_all(year, season), "jikan"
    except Exception as exc:
        rprint(f"[yellow]Jikan failed for {year} {season}: {exc}. Trying AniList fallback...[/yellow]")
        return client.anilist_season_all(year, season), "anilist"


def _raw_season_path(year: int, season: str, payload_source: str) -> Path:
    return RAW / f"{year}_{season}" / f"season_{payload_source}.json"


def _load_cached_payload(year: int, season: str) -> Optional[tuple[dict, str]]:
    """Return a cached raw payload for a season if one exists on disk."""
    season_dir = RAW / f"{year}_{season}"
    if not season_dir.exists():
        return None
    # Prefer jikan cache, then anilist.
    for src in ("jikan", "anilist"):
        p = season_dir / f"season_{src}.json"
        if p.exists():
            try:
                return load_json(p), src
            except Exception:
                continue
    return None


def ingest_one_season(
    year: int,
    season: str,
    source: str = "auto",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch + normalize a single season and append it to anime.parquet.

    Used by the prediction step to ensure the target season (e.g. an upcoming
    season) is present in the normalized store with image URLs. Returns the
    target-season rows.
    """
    load_dotenv()
    client = JikanClient()
    season = season.lower()

    cached = _load_cached_payload(year, season) if use_cache else None
    if cached is not None:
        payload, payload_source = cached
        rprint(f"[dim]  (cache hit: {year}_{season}/season_{payload_source}.json)[/dim]")
    else:
        payload, payload_source = fetch_season_payload(client, year, season, source)
        season_dir = RAW / f"{year}_{season}"
        season_dir.mkdir(parents=True, exist_ok=True)
        save_json(payload, season_dir / f"season_{payload_source}.json")

    df = normalize_season_payload(payload, year, season)
    df["season_key"] = df["year"].astype(str) + "_" + df["season"].astype(str)
    df["source_api"] = payload_source
    merged = _append_to_normalized(df)

    target = merged[(merged["year"] == year) & (merged["season"].astype(str).str.lower() == season)]
    rprint(
        f"[green]{year} {season}: {len(target)} rows "
        f"(normalized store total {len(merged)})[/green]"
    )
    return target.reset_index(drop=True)


def ingest_upcoming(use_cache: bool = False):
    """
    Ingest MAL's 'upcoming' list and append it to anime.parquet.
    """
    load_dotenv()
    client = JikanClient()

    cache_path = RAW / "upcoming" / "upcoming.json"
    payload = None
    if use_cache and cache_path.exists():
        try:
            payload = load_json(cache_path)
            rprint("[cyan]Using cached upcoming payload.[/cyan]")
        except Exception:
            payload = None

    if payload is None:
        rprint("[cyan]Fetching upcoming...[/cyan]")
        try:
            payload = client.seasons_upcoming()
        except Exception as exc:
            rprint(f"[yellow]Jikan upcoming failed: {exc}. Trying AniList fallback...[/yellow]")
            payload = client.anilist_upcoming()

    # Save raw
    save_json(payload, cache_path)

    # Normalize and append
    df = normalize_season_payload(payload, year=None, season="upcoming")
    df["season_key"] = "upcoming"
    merged = _append_to_normalized(df)

    rprint(f"[green]Appended {len(df)} upcoming rows -> {NORMALIZED / 'anime.parquet'} (total {len(merged)})[/green]")


def run_ingest(
    start_year: int,
    end_year: int,
    seasons: List[str],
    source: str = "auto",
    use_cache: bool = False,
):
    """
    Ingest seasons in the given range and append to anime.parquet (no overwrite).

    When ``use_cache`` is True, a season whose raw JSON already exists on disk
    is loaded from cache instead of hitting the API. This makes re-runs fast and
    avoids re-paying Jikan/AniList rate limits.
    """
    load_dotenv()
    client = JikanClient()
    all_dfs: list[pd.DataFrame] = []
    source_mode = source

    for year, season in season_iter(start_year, end_year, seasons):
        rprint(f"[cyan]Fetching {year} {season}...[/cyan]")

        cached = _load_cached_payload(year, season) if use_cache else None
        if cached is not None:
            payload, payload_source = cached
            rprint(f"[dim]  (cache hit: season_{payload_source}.json)[/dim]")
            df = normalize_season_payload(payload, year, season)
            df["season_key"] = df["year"].astype(str) + "_" + df["season"].astype(str)
            df["source_api"] = payload_source
            all_dfs.append(df)
            continue

        season_dir = RAW / f"{year}_{season}"
        season_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload, payload_source = fetch_season_payload(client, year, season, source_mode)
            if source_mode == "auto" and payload_source == "anilist":
                source_mode = "anilist"
                rprint("[yellow]Using AniList for the rest of this ingest run.[/yellow]")
            save_json(payload, season_dir / f"season_{payload_source}.json")
            df = normalize_season_payload(payload, year, season)
            df["season_key"] = df["year"].astype(str) + "_" + df["season"].astype(str)
            df["source_api"] = payload_source
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
    parser.add_argument(
        "--source",
        choices=["auto", "jikan", "anilist"],
        default=os.getenv("INGEST_SOURCE", "auto"),
        help="Season data source. auto tries Jikan first, then falls back to AniList.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Skip API calls for seasons whose raw JSON already exists locally.",
    )
    args = parser.parse_args()

    if args.upcoming:
        ingest_upcoming(use_cache=args.use_cache)
    else:
        if args.start_year is None or args.end_year is None:
            raise SystemExit("When not using --upcoming, you must pass --start-year and --end-year.")
        run_ingest(
            args.start_year,
            args.end_year,
            [s.lower() for s in args.seasons],
            args.source,
            use_cache=args.use_cache,
        )
