from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupShuffleSplit

from ..utils.io import FEATURES, MODELS


@dataclass
class TrainConfig:
    train_start_year: int
    train_end_year: int
    test_year: int


def load_features() -> pd.DataFrame:
    return pd.read_parquet(FEATURES / "features.parquet")


def train_val_test_split(df: pd.DataFrame, cfg: TrainConfig):
    df = df.copy()
    # Filter rows with labels
    df = df[~df["label_score"].isna()].copy()

    # Year-based split
    train = df[(df["year"] >= cfg.train_start_year) & (df["year"] <= cfg.train_end_year)]
    test = df[df["year"] == cfg.test_year]

    # Create a validation split from the tail of the train years (group by season_key to avoid leakage)
    groups = train["season_key"].fillna("unknown")
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(gss.split(train, groups=groups, groups=groups))
    dtrain = train.iloc[train_idx]
    dval = train.iloc[val_idx]

    return dtrain, dval, test


def select_x_y(df: pd.DataFrame):
    cols = json.loads((FEATURES / "feature_columns.json").read_text())
    X = df[cols].copy()
    y = df["label_score"].astype(float).values
    return X, y


def run_train():
    load_dotenv()
    cfg = TrainConfig(
        train_start_year=int(os.getenv("TRAIN_START_YEAR", 2018)),
        train_end_year=int(os.getenv("TRAIN_END_YEAR", 2023)),
        test_year=int(os.getenv("TEST_YEAR", 2024)),
    )

    df = load_features()
    dtrain, dval, dtest = train_val_test_split(df, cfg)

    Xtr, ytr = select_x_y(dtrain)
    Xva, yva = select_x_y(dval)

    model = RandomForestRegressor(
        n_estimators=400,
        max_depth=None,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(Xtr, ytr)

    def eval_split(X, y, name: str):
        pred = model.predict(X)
        mae = mean_absolute_error(y, pred)
        rmse = mean_squared_error(y, pred, squared=False)
        rprint(f"[bold]{name}[/bold]  MAE={mae:.3f}  RMSE={rmse:.3f}")
        return mae, rmse

    eval_split(Xtr, ytr, "Train")
    eval_split(Xva, yva, "Val")

    # Persist model + feature columns
    MODELS.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(model, MODELS / "rf_model.joblib")
    rprint(f"[green]Saved model -> {MODELS / 'rf_model.joblib'}[/green]")


if __name__ == "__main__":
    run_train()