from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from rich import print as rprint

from ..utils.io import NORMALIZED, FEATURES

NUMERIC_DEFAULTS = {
    "episodes": 0,
    "members": 0,
    "favorites": 0,
    "score": np.nan,  # label-like, will not be used as feature for future seasons
}

CATEGORICAL_COLS = ["type", "source", "rating", "season"]
NUMERIC_COLS = ["episodes", "members", "favorites", "year"]
TEXT_COLS = ["title", "synopsis"]


def load_normalized() -> pd.DataFrame:
    path = NORMALIZED / "anime.parquet"
    df = pd.read_parquet(path)
    return df


def simple_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Fill numeric defaults
    for col, val in NUMERIC_DEFAULTS.items():
        if col in df:
            df[col] = df[col].fillna(val)

    # One-hot encode categoricals (keep small)
    cat_df = pd.get_dummies(df[CATEGORICAL_COLS].fillna("unknown"), prefix=CATEGORICAL_COLS, dtype=int)

    # Basic length features
    df["title_len"] = df["title"].fillna("").str.len().clip(0, 200)
    df["synopsis_len"] = df["synopsis"].fillna("").str.len().clip(0, 2000)

    X = pd.concat([df[NUMERIC_COLS + ["title_len", "synopsis_len"]], cat_df], axis=1)

    # Feature hygiene
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    # Save mapping columns for inference time
    FEATURES.mkdir(parents=True, exist_ok=True)
    (FEATURES / "feature_columns.json").write_text(json.dumps(list(X.columns)))

    # Attach id and label columns for downstream
    X.insert(0, "mal_id", df["mal_id"].values)
    X["label_score"] = df.get("score")  # may be NaN for upcoming
    X["season_key"] = df.get("season_key")

    return X


def build():
    df = load_normalized()

    # Derive simple label heuristics: suppose 'score' exists only for finished shows.
    # In a production version you'd compute a stable post-airing score snapshot.

    X = simple_features(df)

    # Train/val/test split by season (time-based)
    # Use the last complete year as test if available
    season_order = (
        X.dropna(subset=["season_key"])  # some upcoming might be NaN
        .groupby("season_key").size().reset_index().sort_values("season_key")
    )

    # Persist features
    X.to_parquet(FEATURES / "features.parquet", index=False)
    rprint(f"[green]Built features: {X.shape} -> {FEATURES / 'features.parquet'}[/green]")


if __name__ == "__main__":
    build()