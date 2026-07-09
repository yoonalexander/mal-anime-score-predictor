from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint

from ..utils.io import NORMALIZED, FEATURES, MODELS, PREDICTIONS
from ..ingest import ingest_one_season

SEASON_ORDER = ["winter", "spring", "summer", "fall"]

# Metadata columns carried into the prediction parquet (for the frontend).
META_COLS = [
    "title", "type", "source", "rating", "episodes", "synopsis",
    "studios", "genres", "themes", "demographics", "image_url", "status",
]


def detect_next_season(df: pd.DataFrame) -> tuple[int, str]:
    seasons = df.dropna(subset=["season", "year"])[["year", "season"]].drop_duplicates()
    seasons["s_idx"] = seasons["season"].astype(str).str.lower().map(
        {s: i for i, s in enumerate(SEASON_ORDER)}
    )
    seasons = seasons.sort_values(["year", "s_idx"]).reset_index(drop=True)
    last = seasons.iloc[-1]
    s_pos = int(last["s_idx"]) + 1
    year = int(last["year"]) + (1 if s_pos >= 4 else 0)
    season = SEASON_ORDER[s_pos % 4]
    return year, season


def load_feature_columns() -> list[str]:
    return json.loads((FEATURES / "feature_columns.json").read_text())


def _studio_name(cell) -> str:
    if cell is None:
        return ""
    try:
        if isinstance(cell, float) and np.isnan(cell):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(cell, str) and cell:
        return cell
    # Handle numpy arrays, lists, tuples.
    try:
        seq = list(cell)
    except TypeError:
        return ""
    if seq:
        first = seq[0]
        if isinstance(first, dict):
            return first.get("name") or ""
        return str(first)
    return ""


def _list_to_names(cell) -> list[str]:
    out = []
    if cell is None:
        return out
    try:
        if isinstance(cell, float) and np.isnan(cell):
            return out
    except (TypeError, ValueError):
        pass
    if isinstance(cell, str):
        return [cell] if cell else out
    try:
        seq = list(cell)
    except TypeError:
        return out
    for it in seq:
        if isinstance(it, dict):
            n = it.get("name")
            if n:
                out.append(n)
        elif isinstance(it, str):
            out.append(it)
    return out


def _ensure_target_season(year: int, season: str) -> None:
    """Make sure the target season exists in the normalized store with images."""
    norm = NORMALIZED / "anime.parquet"
    if not norm.exists():
        raise SystemExit(f"Missing {norm}. Run ingest first.")
    df = pd.read_parquet(norm)
    target = df[(df["year"] == year) & (df["season"].astype(str).str.lower() == season.lower())]
    if not target.empty:
        return
    rprint(f"[cyan]Target season {year} {season} not in normalized data; fetching it...[/cyan]")
    ingest_one_season(year, season, source=os.getenv("INGEST_SOURCE", "auto"), use_cache=True)


def predict_for_season(year: int, season: str, fetch_if_missing: bool = True):
    season = season.lower()

    if fetch_if_missing:
        _ensure_target_season(year, season)

    df = pd.read_parquet(NORMALIZED / "anime.parquet")
    target = df[(df["year"] == year) & (df["season"].astype(str).str.lower() == season)].copy()
    if target.empty:
        rprint(f"[yellow]No rows for {year} {season} in normalized data. Run ingest first.[/yellow]")
        return None

    # Build features using the same transformation used during training.
    X_all = pd.read_parquet(FEATURES / "features.parquet")
    cols = load_feature_columns()

    features = (
        X_all.merge(target[["mal_id"]], on="mal_id", how="right")
        .set_index("mal_id")
        .reindex(columns=cols)
        .fillna(0)
    )

    model_path = MODELS / "model.joblib"
    if not model_path.exists():
        model_path = MODELS / "rf_model.joblib"
    if not model_path.exists():
        raise SystemExit("Missing trained model. Run `python -m src.models.train` first.")
    model = joblib.load(model_path)
    preds = model.predict(features)

    # Uncertainty estimate:
    # - Tree ensembles (RF / GBR / LightGBM) expose per-tree predictions.
    # - Ridge has no trees; fall back to a fixed band from validation MAE.
    pred_std = np.zeros(len(preds))
    if hasattr(model, "estimators_") and len(getattr(model, "estimators_", [])) > 1:
        # RandomForest: list of trees
        tree_preds = np.stack([t.predict(features) for t in model.estimators_])
        pred_std = tree_preds.std(axis=0)
    elif hasattr(model, "_predictors") and getattr(model, "_predictors", None):
        # HistGradientBoosting keeps raw predictors; use loss-based fallback instead.
        pred_std = np.full(len(preds), 0.25)
    else:
        pred_std = np.full(len(preds), 0.25)

    out_df = target[["mal_id", "title", "year", "season"]].copy()
    out_df["pred_score"] = np.round(preds, 3)
    out_df["pred_low"] = np.round(preds - 1.96 * pred_std, 3)
    out_df["pred_high"] = np.round(preds + 1.96 * pred_std, 3)

    # Carry rich metadata for the frontend.
    for col in META_COLS:
        out_df[col] = target[col].values if col in target.columns else None

    out_df["studio"] = target["studios"].apply(_studio_name).values if "studios" in target.columns else ""
    out_df["genres_list"] = target["genres"].apply(_list_to_names).values if "genres" in target.columns else None
    out_df["themes_list"] = target["themes"].apply(_list_to_names).values if "themes" in target.columns else None
    out_df["mal_url"] = "https://myanimelist.net/anime/" + out_df["mal_id"].astype(str)

    PREDICTIONS.mkdir(parents=True, exist_ok=True)
    out_path = PREDICTIONS / f"predictions_{year}_{season}.parquet"
    out_df.to_parquet(out_path, index=False)
    rprint(f"[green]Saved predictions -> {out_path} ({len(out_df)} rows)[/green]")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="auto", help="Format: 'YEAR:SEASON' or 'auto'")
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="Do not fetch the target season from the API if it is missing locally.",
    )
    args = parser.parse_args()

    load_dotenv()
    df_norm = pd.read_parquet(NORMALIZED / "anime.parquet")

    if args.season == "auto":
        y, s = detect_next_season(df_norm)
    elif ":" in args.season:
        y_str, s = args.season.split(":", 1)
        y = int(y_str)
    else:
        raise SystemExit("--season must be 'auto' or 'YEAR:SEASON', e.g., 2026:summer")

    predict_for_season(y, s, fetch_if_missing=not args.no_fetch)
