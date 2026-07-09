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


def row_to_frontend_obj(row) -> dict:
    """Map one prediction row to the JSON shape the frontend expects."""
    score = float(row.pred_score) if pd.notna(row.pred_score) else None
    pred_low = float(row.pred_low) if "pred_low" in row._asdict() and pd.notna(row.pred_low) else None
    pred_high = float(row.pred_high) if "pred_high" in row._asdict() and pd.notna(row.pred_high) else None

    return {
        "mal_id": int(row.mal_id),
        "title": row.title,
        "year": int(row.year) if pd.notna(row.year) else None,
        "season": str(row.season),
        "pred_score": round(score, 2) if score is not None else None,
        "pred_low": round(pred_low, 2) if pred_low is not None else None,
        "pred_high": round(pred_high, 2) if pred_high is not None else None,
        "image_url": getattr(row, "image_url", None),
        "genres": list(row.genres_list) if "genres_list" in row._asdict() and row.genres_list is not None else [],
        "themes": list(row.themes_list) if "themes_list" in row._asdict() and row.themes_list is not None else [],
        "studio": getattr(row, "studio", "") or "",
        "source": getattr(row, "source", None),
        "type": getattr(row, "type", None),
        "episodes": int(row.episodes) if "episodes" in row._asdict() and pd.notna(row.episodes) else None,
        "rating": getattr(row, "rating", None),
        "status": getattr(row, "status", None),
        "synopsis": getattr(row, "synopsis", None),
        "mal_url": getattr(row, "mal_url", None)
        or (f"https://myanimelist.net/anime/{int(row.mal_id)}" if pd.notna(row.mal_id) else None),
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
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
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
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
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
