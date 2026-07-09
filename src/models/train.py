from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from rich import print as rprint
from rich.table import Table
from sklearn.ensemble import (
    RandomForestRegressor,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ..utils.io import FEATURES, MODELS


@dataclass
class TrainConfig:
    train_start_year: int
    train_end_year: int
    val_year: int
    test_year: int


def load_features() -> pd.DataFrame:
    return pd.read_parquet(FEATURES / "features.parquet")


def load_feature_columns() -> list[str]:
    return json.loads((FEATURES / "feature_columns.json").read_text())


def chronological_split(df: pd.DataFrame, cfg: TrainConfig):
    """Time-based split that mirrors the real prediction task.

    train: years [train_start_year, train_end_year]
    val:   cfg.val_year          (the most recent completed year before test)
    test:  cfg.test_year         (held out, reported but never trained on)

    Rows without a label are dropped (they are upcoming/un-scored).
    """
    df = df.copy()
    df = df[df["label_score"].notna()].copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")

    train = df[(df["year"] >= cfg.train_start_year) & (df["year"] <= cfg.train_end_year)]
    val = df[df["year"] == cfg.val_year]
    test = df[df["year"] == cfg.test_year]

    if train.empty:
        raise SystemExit("Train split is empty. Check TRAIN_START_YEAR/TRAIN_END_YEAR and ingested data.")
    if val.empty:
        rprint(f"[yellow]Warning: validation year {cfg.val_year} has no labeled rows.[/yellow]")
    if test.empty:
        rprint(f"[yellow]Warning: test year {cfg.test_year} has no labeled rows.[/yellow]")

    return train, val, test


def select_x_y(df: pd.DataFrame, cols: list[str]):
    X = df[cols].copy()
    y = df["label_score"].astype(float).values
    return X, y


def _eval(model, X, y, name: str) -> dict:
    pred = model.predict(X)
    mae = mean_absolute_error(y, pred)
    rmse = float(np.sqrt(mean_squared_error(y, pred)))
    r2 = r2_score(y, pred) if len(y) > 1 else float("nan")
    rprint(f"[bold]{name:<6}[/bold]  MAE={mae:.3f}  RMSE={rmse:.3f}  R2={r2:.3f}")
    return {"name": name, "mae": mae, "rmse": rmse, "r2": r2}


def _candidate_models() -> dict:
    """Models to compare. LightGBM is used if available; otherwise skipped."""
    models = {
        "random_forest": RandomForestRegressor(
            n_estimators=400, max_depth=None, min_samples_leaf=3,
            random_state=42, n_jobs=-1,
        ),
        "hist_gbr": HistGradientBoostingRegressor(
            max_iter=500, learning_rate=0.05, max_depth=None,
            min_samples_leaf=20, l2_regularization=1.0, random_state=42,
        ),
        "ridge": Ridge(alpha=10.0, random_state=42),
    }
    try:
        from lightgbm import LGBMRegressor  # type: ignore

        models["lightgbm"] = LGBMRegressor(
            n_estimators=600, learning_rate=0.03, num_leaves=31,
            min_child_samples=20, reg_lambda=1.0, random_state=42, n_jobs=-1,
            verbosity=-1,
        )
    except Exception:
        rprint("[dim]lightgbm not installed; skipping it.[/dim]")
    return models


def run_train():
    load_dotenv()
    cfg = TrainConfig(
        train_start_year=int(os.getenv("TRAIN_START_YEAR", 2018)),
        train_end_year=int(os.getenv("TRAIN_END_YEAR", 2023)),
        val_year=int(os.getenv("VAL_YEAR", 2024)),
        test_year=int(os.getenv("TEST_YEAR", 2025)),
    )
    rprint(f"[cyan]Config: train {cfg.train_start_year}-{cfg.train_end_year}, "
           f"val {cfg.val_year}, test {cfg.test_year}[/cyan]")

    df = load_features()
    cols = load_feature_columns()
    dtrain, dval, dtest = chronological_split(df, cfg)

    Xtr, ytr = select_x_y(dtrain, cols)
    Xva, yva = select_x_y(dval, cols)
    Xte, yte = select_x_y(dtest, cols)

    rprint(f"[dim]train={len(Xtr)} val={len(Xva)} test={len(Xte)} features={len(cols)}[/dim]")

    results: dict[str, dict] = {}
    fitted: dict = {}
    for name, model in _candidate_models().items():
        rprint(f"\n[magenta]== Training {name} ==[/magenta]")
        model.fit(Xtr, ytr)
        fitted[name] = model
        results[name] = {
            "train": _eval(model, Xtr, ytr, "train"),
            "val": _eval(model, Xva, yva, "val"),
            "test": _eval(model, Xte, yte, "test") if len(Xte) else None,
        }

    # Pick best by validation MAE.
    best_name = min(
        (n for n in results if results[n]["val"] is not None),
        key=lambda n: results[n]["val"]["mae"],
    )
    best_model = fitted[best_name]
    rprint(f"\n[bold green]Best model by val MAE: {best_name}[/bold green]")

    # Persist the best model + metadata.
    import joblib

    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODELS / "model.joblib")
    # Keep the old filename for backward compatibility with any old scripts.
    joblib.dump(best_model, MODELS / "rf_model.joblib")

    meta = {
        "best_model": best_name,
        "feature_columns": cols,
        "config": cfg.__dict__,
        "results": results,
    }
    (MODELS / "metrics.json").write_text(json.dumps(meta, indent=2, default=float))
    rprint(f"[green]Saved model -> {MODELS / 'model.joblib'}[/green]")
    rprint(f"[green]Saved metrics -> {MODELS / 'metrics.json'}[/green]")

    # Pretty summary table.
    t = Table(title="Model comparison (val)", show_header=True, header_style="bold")
    t.add_column("Model")
    t.add_column("MAE", justify="right")
    t.add_column("RMSE", justify="right")
    t.add_column("R2", justify="right")
    for name, r in results.items():
        v = r["val"]
        if v is None:
            continue
        t.add_row(name, f"{v['mae']:.3f}", f"{v['rmse']:.3f}", f"{v['r2']:.3f}")
    rprint(t)


if __name__ == "__main__":
    run_train()
