from __future__ import annotations
import argparse, json
from pathlib import Path

import pandas as pd
from rich import print as rprint
from rich.table import Table

from .io import NORMALIZED, FEATURES, MODELS, PREDICTIONS

def exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False

def safe_read_parquet(p: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()

def parse_season_arg(arg: str | None) -> tuple[int | None, str | None]:
    if not arg:
        return None, None
    if arg == "auto":
        return None, "auto"
    if ":" in arg:
        y, s = arg.split(":", 1)
        return int(y), s.lower()
    raise SystemExit("--season must be 'YEAR:SEASON', e.g., 2025:fall, or 'auto'")

def detect_next_season(df_norm: pd.DataFrame) -> tuple[int, str]:
    SEASON_ORDER = ["winter", "spring", "summer", "fall"]
    s2i = {s: i for i, s in enumerate(SEASON_ORDER)}
    df = df_norm.dropna(subset=["year", "season"]).copy()
    if df.empty:
        from datetime import datetime
        return datetime.now().year, "winter"
    df["season"] = df["season"].astype(str).str.lower()
    df["s_idx"] = df["season"].map(s2i)
    df = df.sort_values(["year", "s_idx"])
    last = df.iloc[-1]
    s_pos = int(last["s_idx"]) + 1
    year = int(last["year"]) + (1 if s_pos >= 4 else 0)
    season = SEASON_ORDER[s_pos % 4]
    return year, season

def main():
    ap = argparse.ArgumentParser(description="Show MAL predictor data/status and what’s missing.")
    ap.add_argument("--season", default=None, help="Check predictions for 'YEAR:SEASON' or 'auto'")
    args = ap.parse_args()
    season_year, season_name = parse_season_arg(args.season)

    # Files
    f_norm = NORMALIZED / "anime.parquet"
    f_labels = NORMALIZED / "labels.parquet"
    f_feat = FEATURES / "features.parquet"
    f_model = MODELS / "rf_model.joblib"

    # Read what exists
    df_norm = safe_read_parquet(f_norm) if exists(f_norm) else pd.DataFrame()
    df_labels = safe_read_parquet(f_labels) if exists(f_labels) else pd.DataFrame()
    df_feat = safe_read_parquet(f_feat) if exists(f_feat) else pd.DataFrame()
    model_exists = exists(f_model)

    # Stats
    norm_rows = len(df_norm)
    seasons_present = (
        df_norm[["year", "season"]].dropna().drop_duplicates().sort_values(["year", "season"]).tail(8)
        if norm_rows else pd.DataFrame()
    )
    labeled = int(df_feat["label_score"].notna().sum()) if not df_feat.empty and "label_score" in df_feat else 0

    # Season target
    if season_name == "auto" and not df_norm.empty:
        season_year, season_name = detect_next_season(df_norm)
    pred_file = None
    if season_year and season_name:
        pred_file = PREDICTIONS / f"predictions_{season_year}_{season_name}.parquet"

    # Output
    rprint("[bold cyan]Project status[/bold cyan]")

    t = Table(show_header=True, header_style="bold")
    t.add_column("Artifact")
    t.add_column("Exists")
    t.add_column("Details")

    t.add_row(
        "Normalized (anime.parquet)",
        "✅" if norm_rows else "❌",
        f"{norm_rows} rows" if norm_rows else "missing → run ingest",
    )
    t.add_row(
        "Labels (labels.parquet)",
        "✅" if not df_labels.empty else "❌",
        f"{len(df_labels)} rows" if not df_labels.empty else "missing/empty → run ingest_details",
    )
    t.add_row(
        "Features (features.parquet)",
        "✅" if not df_feat.empty else "❌",
        f"{len(df_feat)} rows; labeled={labeled}" if not df_feat.empty else "missing → run build_features",
    )
    t.add_row(
        "Model (rf_model.joblib)",
        "✅" if model_exists else "❌",
        "ready" if model_exists else "missing → run train",
    )

    if season_year and season_name:
        preds_exist = exists(pred_file or Path(""))
        t.add_row(
            f"Predictions for {season_year} {season_name}",
            "✅" if preds_exist else "❌",
            f"{pred_file}" if preds_exist else "missing → run predict",
        )

    rprint(t)

    if not seasons_present.empty:
        rprint("\n[bold]Recent seasons in normalized:[/bold]")
        print(seasons_present.to_string(index=False))

    rprint("\n[bold magenta]Next actions[/bold magenta]")
    if norm_rows == 0:
        rprint("• Run: [green]python -m src.ingest --start-year 2012 --end-year 2024 --seasons winter spring summer fall[/green]")
        rprint("• (then append) [green]python -m src.ingest --start-year 2025 --end-year 2025 --seasons fall[/green]")
        return
    if df_labels.empty:
        rprint("• Run: [green]python -m src.ingest_details --year-min 2018 --year-max 2024[/green]")
    if df_feat.empty or "label_score" not in df_feat:
        rprint("• Run: [green]python -m src.features.build_features[/green]")
    if not model_exists and (not df_feat.empty and labeled > 0):
        rprint("• Run: [green]python -m src.models.train[/green]")
    if season_year and season_name and not exists(pred_file or Path("")) and model_exists:
        rprint(f"• Run: [green]python -m src.models.predict --season {season_year}:{season_name}[/green]")

if __name__ == "__main__":
    main()
