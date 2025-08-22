from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from rich import print as rprint

from ..utils.io import NORMALIZED, FEATURES, MODELS, PREDICTIONS


SEASON_ORDER = ["winter", "spring", "summer", "fall"]


def detect_next_season(df: pd.DataFrame) -> tuple[int, str]:
    # Simple heuristic: find max (year, season) that exists, then return the next season chronologically
    seasons = df.dropna(subset=["season", "year"])[["year", "season"]].drop_duplicates()
    seasons["s_idx"] = seasons["season"].map({s: i for i, s in enumerate(SEASON_ORDER)})
    seasons = seasons.sort_values(["year", "s_idx"]).reset_index(drop=True)
    last = seasons.iloc[-1]
    s_pos = int(last["s_idx"]) + 1
    year = int(last["year"]) + (1 if s_pos >= 4 else 0)
    season = SEASON_ORDER[s_pos % 4]
    return year, season


def load_feature_columns():
    return json.loads((FEATURES / "feature_columns.json").read_text())


def predict_for_season(year: int, season: str):
    # Load normalized and select rows that match the target season and have no score (upcoming or airing)
    df = pd.read_parquet(NORMALIZED / "anime.parquet")
    target = df[(df["year"] == year) & (df["season"].str.lower() == season.lower())].copy()
    if target.empty:
        rprint(f"[yellow]No rows for {year} {season} in normalized data. Run ingest first.[/yellow]")
        return

    # Build features using the same transformation used during training
    X_all = pd.read_parquet(FEATURES / "features.parquet")
    cols = load_feature_columns()

    features = (
        X_all.merge(target[["mal_id"]], on="mal_id", how="right")
        .set_index("mal_id")
        .reindex(columns=cols)
        .fillna(0)
    )

    model = joblib.load(MODELS / "rf_model.joblib")
    preds = model.predict(features.values)

    out_df = target[["mal_id", "title", "year", "season"]].copy()
    out_df["pred_score"] = preds

    PREDICTIONS.mkdir(parents=True, exist_ok=True)
    out_path = PREDICTIONS / f"predictions_{year}_{season.lower()}.parquet"
    out_df.to_parquet(out_path, index=False)
    rprint(f"[green]Saved predictions -> {out_path} ({len(out_df)} rows)[/green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="auto", help="Format: 'YEAR:SEASON' or 'auto'")
    args = parser.parse_args()

    df_norm = pd.read_parquet(NORMALIZED / "anime.parquet")

    if args.season == "auto":
        y, s = detect_next_season(df_norm)
    elif ":" in args.season:
        y_str, s = args.season.split(":", 1)
        y = int(y_str)
    else:
        raise SystemExit("--season must be 'auto' or 'YEAR:SEASON', e.g., 2025:fall")

    predict_for_season(y, s)
