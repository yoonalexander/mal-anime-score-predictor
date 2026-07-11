"""Export prediction parquets into committed frontend JSON artifacts.

The frontend reads static JSON from ``anime-frontend/public/predictions/`` so
the deployed Vercel site needs no backend. This script turns each prediction
parquet into a JSON array the React app can consume, and maintains an
``index.json`` listing the available seasons.

Usage:
    python -m src.export_predictions                 # export all prediction parquets
    python -m src.export_predictions --season 2026:summer
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from rich import print as rprint

from .utils.io import PREDICTIONS

FRONTEND_PRED_DIR = (
    Path(__file__).resolve().parents[1] / "anime-frontend" / "public" / "predictions"
)

SEASON_LABELS = {
    "winter": "Winter",
    "spring": "Spring",
    "summer": "Summer",
    "fall": "Fall",
}


def _season_filename(year: int, season: str) -> str:
    return f"{year}-{season.lower()}.json"


def _clean(value):
    """Coerce pandas NaN/NaT to None so json.dumps emits valid JSON null.

    Python's json.dumps writes the literal ``NaN`` by default, which is NOT valid
    JSON and throws under JavaScript's JSON.parse(). Any float NaN, float('nan'),
    or pandas NA/NaT must become None.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def row_to_frontend_obj(row) -> dict:
    """Map one prediction row to the JSON shape the frontend expects."""
    fields = row._asdict()
    score = _clean(fields.get("pred_score"))
    pred_low = _clean(fields.get("pred_low"))
    pred_high = _clean(fields.get("pred_high"))
    episodes = _clean(fields.get("episodes"))

    genres_list = _clean(fields.get("genres_list"))
    themes_list = _clean(fields.get("themes_list"))

    def _to_list(v):
        if v is None:
            return []
        try:
            return [str(x) for x in list(v)]
        except TypeError:
            return [str(v)]

    return {
        "mal_id": int(row.mal_id),
        "title": _clean(row.title) or "",
        "year": int(row.year) if _clean(row.year) is not None else None,
        "season": str(_clean(row.season) or ""),
        "pred_score": round(float(score), 2) if score is not None else None,
        "pred_low": round(float(pred_low), 2) if pred_low is not None else None,
        "pred_high": round(float(pred_high), 2) if pred_high is not None else None,
        "image_url": _clean(fields.get("image_url")),
        "genres": _to_list(genres_list),
        "themes": _to_list(themes_list),
        "studio": _clean(fields.get("studio")) or "",
        "source": _clean(fields.get("source")),
        "type": _clean(fields.get("type")),
        "episodes": int(episodes) if episodes is not None else None,
        "rating": _clean(fields.get("rating")),
        "status": _clean(fields.get("status")),
        "synopsis": _clean(fields.get("synopsis")),
        "mal_url": _clean(fields.get("mal_url"))
        or (f"https://myanimelist.net/anime/{int(row.mal_id)}" if _clean(row.mal_id) is not None else None),
    }


def export_one(parquet_path: Path) -> Optional[dict]:
    if not parquet_path.exists():
        rprint(f"[yellow]Missing {parquet_path}[/yellow]")
        return None

    df = pd.read_parquet(parquet_path)
    if df.empty:
        rprint(f"[yellow]{parquet_path.name} is empty.[/yellow]")
        return None

    # Sort by predicted score descending for a sensible default order.
    if "pred_score" in df.columns:
        df = df.sort_values("pred_score", ascending=False).reset_index(drop=True)

    items = [row_to_frontend_obj(row) for row in df.itertuples(index=False)]

    # Parse year + season from the filename: predictions_<year>_<season>.parquet
    stem = parquet_path.stem  # e.g. predictions_2026_summer
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0] == "predictions":
        year = int(parts[1])
        season = parts[2].lower()
    else:
        year = int(df["year"].iloc[0]) if "year" in df.columns else 0
        season = str(df["season"].iloc[0]).lower() if "season" in df.columns else "unknown"

    FRONTEND_PRED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FRONTEND_PRED_DIR / _season_filename(year, season)
    out_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    rprint(f"[green]Wrote {len(items)} items -> {out_path}[/green]")

    return {
        "year": year,
        "season": season,
        "label": f"{SEASON_LABELS.get(season, season.title())} {year}",
        "file": f"{_season_filename(year, season)}",
        "count": len(items),
    }


def write_index(entries: list[dict]) -> None:
    """Write index.json listing seasons, newest first."""
    entries = sorted(entries, key=lambda e: (e["year"], {"winter": 0, "spring": 1, "summer": 2, "fall": 3}.get(e["season"], 4)), reverse=True)
    FRONTEND_PRED_DIR.mkdir(parents=True, exist_ok=True)
    (FRONTEND_PRED_DIR / "index.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    rprint(f"[green]Wrote index -> {FRONTEND_PRED_DIR / 'index.json'} ({len(entries)} seasons)[/green]")


def export_all():
    parquets = sorted(PREDICTIONS.glob("predictions_*.parquet"))
    if not parquets:
        rprint("[yellow]No prediction parquets found in data/predictions/.[/yellow]")
        return
    entries = []
    for p in parquets:
        entry = export_one(p)
        if entry:
            entries.append(entry)
    write_index(entries)


def export_season(year: int, season: str):
    p = PREDICTIONS / f"predictions_{year}_{season.lower()}.parquet"
    entry = export_one(p)
    if entry:
        # Rebuild index from all existing exports + this one.
        existing = json.loads((FRONTEND_PRED_DIR / "index.json").read_text()) if (FRONTEND_PRED_DIR / "index.json").exists() else []
        existing = [e for e in existing if not (e["year"] == entry["year"] and e["season"] == entry["season"])]
        existing.append(entry)
        write_index(existing)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default=None, help="Format: 'YEAR:SEASON'. If omitted, export all.")
    args = parser.parse_args()

    if args.season:
        if ":" not in args.season:
            raise SystemExit("--season must be 'YEAR:SEASON', e.g., 2026:summer")
        y_str, s = args.season.split(":", 1)
        export_season(int(y_str), s.lower())
    else:
        export_all()
