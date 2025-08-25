from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from rich import print as rprint

from .mal.client import JikanClient
from .utils.io import RAW, NORMALIZED

DETAILS_DIR = RAW / "details"
DETAILS_DIR.mkdir(parents=True, exist_ok=True)


def load_candidates(year_min: Optional[int], year_max: Optional[int]) -> pd.DataFrame:
    """
    Load candidate MAL IDs from anime.parquet, filter by year if provided,
    and skip IDs we already labeled (labels.parquet).
    """
    norm_path = NORMALIZED / "anime.parquet"
    if not norm_path.exists():
        raise SystemExit(f"Missing {norm_path}. Run ingest first.")

    df = pd.read_parquet(norm_path)[["mal_id", "year", "season", "title"]].drop_duplicates()

    # Year filters are best-effort (some rows may have NaN year)
    if year_min is not None:
        df = df[(df["year"].isna()) | (df["year"] >= year_min)]
    if year_max is not None:
        df = df[(df["year"].isna()) | (df["year"] <= year_max)]

    # Skip IDs we already labeled
    labels_path = NORMALIZED / "labels.parquet"
    if labels_path.exists():
        lab = pd.read_parquet(labels_path)
        have = set(lab["mal_id"].astype(int)) if "mal_id" in lab.columns else set()
        df = df[~df["mal_id"].astype(int).isin(have)]

    return df.reset_index(drop=True)


def cache_path(mal_id: int) -> Path:
    return DETAILS_DIR / f"{mal_id}.json"


def fetch_detail(client: JikanClient, mal_id: int) -> dict | None:
    """
    Return details payload from cache if available, falling back to the API.
    """
    cp = cache_path(mal_id)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupt cache; re-fetch

    try:
        payload = client.anime(mal_id)  # JikanClient has retries/backoff/cooldown
        cp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    except Exception as e:
        rprint(f"[yellow]skip {mal_id}: {e}[/yellow]")
        return None


def extract_label(payload: dict) -> dict | None:
    d = payload.get("data") or {}
    mid = d.get("mal_id")
    if mid is None:
        return None
    score = d.get("score", d.get("scored"))
    try:
        mid = int(mid)
    except Exception:
        return None
    try:
        score = float(score) if score is not None else None
    except Exception:
        score = None
    return {
        "mal_id": mid,
        "final_score": score,
        "members_detail": d.get("members"),
        "favorites_detail": d.get("favorites"),
    }


def backfill_labels(year_min: Optional[int], year_max: Optional[int]):
    df = load_candidates(year_min, year_max)
    if df.empty:
        rprint("[yellow]No candidates to fetch (all labeled or none match filters).[/yellow]")
        return

    rprint(f"[cyan]Fetching details for {len(df)} titles...[/cyan]")
    client = JikanClient()

    new_rows = []
    for i, row in enumerate(df.itertuples(index=False), 1):
        mal_id = int(row.mal_id)
        p = fetch_detail(client, mal_id)
        if p is None:
            continue
        lab = extract_label(p)
        if lab is not None:
            new_rows.append(lab)

        if i % 200 == 0:
            rprint(f"[cyan]{i}/{len(df)} fetched...[/cyan]")

    lab_new = pd.DataFrame(new_rows).drop_duplicates("mal_id")

    # Merge with existing labels (resume support)
    labels_path = NORMALIZED / "labels.parquet"
    if labels_path.exists():
        lab_old = pd.read_parquet(labels_path)
        lab = (
            pd.concat([lab_old, lab_new], ignore_index=True)
            .drop_duplicates("mal_id", keep="last")
            .reset_index(drop=True)
        )
    else:
        lab = lab_new

    lab.to_parquet(labels_path, index=False)
    rprint(f"[green]Wrote labels -> {labels_path} ({len(lab)} rows total; +{len(lab_new)} new)[/green]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year-min", type=int, default=None, help="Only fetch anime with year >= this (if available)")
    ap.add_argument("--year-max", type=int, default=None, help="Only fetch anime with year <= this (if available)")
    args = ap.parse_args()
    backfill_labels(args.year_min, args.year_max)
