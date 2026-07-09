from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from rich import print as rprint

from ..utils.io import NORMALIZED, FEATURES

# ---------------------------------------------------------------------------
# Feature design (leakage-safe for pre-/early-season prediction)
# ---------------------------------------------------------------------------
# We deliberately EXCLUDE `members`, `favorites`, `score`, and any other field
# whose value is only meaningful *after* a show has aired and accumulated an
# audience. Those would leak the target. The features below are all knowable
# before a season begins:
#   - studio, genres, themes, demographics, source, type, rating, season, year
#   - episode count (announced pre-release), title/synopsis length
#
# `score` is kept ONLY as the training label (`label_score`), never as a feature.

CATEGORICAL_COLS = ["type", "source", "rating", "season"]
NUMERIC_COLS = ["episodes", "year"]
TEXT_COLS = ["title", "synopsis"]

# Top-N cap for multi-hot encoded list columns (keeps feature space bounded).
TOP_N_GENRES = 20
TOP_N_THEMES = 20
TOP_N_STUDIOS = 30
TOP_N_DEMOGRAPHICS = 10


def _names(cell):
    """Coerce a list-of-dicts or list-of-strings cell into a list of names."""
    if cell is None:
        return []
    out = []
    if isinstance(cell, float) and np.isnan(cell):
        return out
    if isinstance(cell, str):
        return [cell]
    for it in cell:
        if isinstance(it, dict):
            n = it.get("name")
            if n:
                out.append(n)
        elif isinstance(it, str):
            out.append(it)
    return out


def _top_value_counts(series: pd.Series, top_n: int) -> list[str]:
    """Return the top-N most frequent individual names across a list-cell series."""
    counter = {}
    for cell in series:
        for n in _names(cell):
            counter[n] = counter.get(n, 0) + 1
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]]


def _multihot(series: pd.Series, vocab: list[str]) -> pd.DataFrame:
    """Build a 0/1 multi-hot DataFrame for list-valued cells against ``vocab``."""
    if not vocab:
        return pd.DataFrame(index=series.index)
    cols = {f"{series.name}_{v}": [] for v in vocab}
    for cell in series:
        names = set(_names(cell))
        for v in vocab:
            cols[f"{series.name}_{v}"].append(1 if v in names else 0)
    return pd.DataFrame(cols, index=series.index).astype(int)


def load_normalized() -> pd.DataFrame:
    path = NORMALIZED / "anime.parquet"
    df = pd.read_parquet(path)
    return df


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Backfill optional columns so old (AniList-only) snapshots still work."""
    n = len(df)
    defaults = {
        "themes": [[] for _ in range(n)],
        "image_url": [None] * n,
        "images": [None] * n,
        "source_api": [None] * n,
        "season_key": [None] * n,
        "demographics": [[] for _ in range(n)],
    }
    for col, vals in defaults.items():
        if col not in df.columns:
            df[col] = vals
    return df


def simple_features(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_columns(df.copy())

    # --- numeric ---
    # episodes: log1p, missing -> median of known values
    eps = pd.to_numeric(df["episodes"], errors="coerce")
    eps_known = eps[eps.notna() & (eps > 0)]
    eps_fill = float(eps_known.median()) if not eps_known.empty else 12.0
    df["episodes_log"] = np.log1p(eps.fillna(eps_fill).clip(lower=0))
    df["episodes_missing"] = eps.isna().astype(int)

    # year
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    year_known = df["year"].dropna()
    year_fill = int(year_known.median()) if not year_known.empty else 2020
    df["year_filled"] = df["year"].fillna(year_fill).astype(int)

    # --- text length features ---
    title_len = df["title"].fillna("").astype(str).str.len().clip(0, 200)
    syn = df["synopsis"].fillna("").astype(str)
    df["title_len"] = title_len
    df["synopsis_len"] = syn.str.len().clip(0, 2000)
    df["synopsis_log"] = np.log1p(df["synopsis_len"])
    df["synopsis_missing"] = (syn.str.len() == 0).astype(int)
    # crude keyword signal: presence of "season 2"/"season 3"/"part 2"/"II"/"III"
    sequel_pat = r"(?:season\s*[2-9]|part\s*[2-9]|\bii\b|\biii\b|\biv\b|\bv\b|2nd|3rd|4th)"
    df["title_suggests_sequel"] = (
        df["title"].fillna("").astype(str).str.lower().str.contains(sequel_pat, regex=True).astype(int)
    )

    # --- categorical one-hot ---
    cat_df = pd.get_dummies(
        df[CATEGORICAL_COLS].fillna("unknown").astype(str),
        prefix=CATEGORICAL_COLS,
        dtype=int,
    )

    # --- multi-hot list columns (top-N by frequency) ---
    genre_vocab = _top_value_counts(df["genres"], TOP_N_GENRES)
    theme_vocab = _top_value_counts(df["themes"], TOP_N_THEMES)
    studio_vocab = _top_value_counts(df["studios"], TOP_N_STUDIOS)
    demo_vocab = _top_value_counts(df["demographics"], TOP_N_DEMOGRAPHICS)

    genre_mh = _multihot(df["genres"].rename("genre"), genre_vocab)
    theme_mh = _multihot(df["themes"].rename("theme"), theme_vocab)
    studio_mh = _multihot(df["studios"].rename("studio"), studio_vocab)
    demo_mh = _multihot(df["demographics"].rename("demo"), demo_vocab)

    base = pd.concat(
        [
            df[["episodes_log", "episodes_missing", "year_filled", "title_len", "synopsis_log",
                "synopsis_missing", "title_suggests_sequel"]],
            cat_df,
            genre_mh,
            theme_mh,
            studio_mh,
            demo_mh,
        ],
        axis=1,
    )

    # Feature hygiene
    base = base.replace([np.inf, -np.inf], np.nan).fillna(0)

    # Persist the feature column list + the multi-hot vocabularies for inference.
    FEATURES.mkdir(parents=True, exist_ok=True)
    (FEATURES / "feature_columns.json").write_text(json.dumps(list(base.columns)))
    (FEATURES / "vocab.json").write_text(
        json.dumps(
            {
                "genres": genre_vocab,
                "themes": theme_vocab,
                "studios": studio_vocab,
                "demographics": demo_vocab,
                "episodes_fill": eps_fill,
                "year_fill": year_fill,
            }
        )
    )

    # Attach id/label columns for downstream training/prediction.
    base.insert(0, "mal_id", df["mal_id"].values)
    base["label_score"] = pd.to_numeric(df.get("score"), errors="coerce")
    base["season_key"] = df.get("season_key")
    base["year"] = df["year"].values
    base["season"] = df["season"].values

    # Carry display/metadata forward for the prediction export step.
    for meta_col in ["title", "type", "source", "rating", "episodes", "synopsis",
                     "studios", "genres", "themes", "demographics", "image_url",
                     "images", "members", "favorites", "status", "source_api"]:
        if meta_col in df.columns:
            base[meta_col] = df[meta_col].values

    return base


def build():
    df = load_normalized()
    X = simple_features(df)
    X.to_parquet(FEATURES / "features.parquet", index=False)
    rprint(f"[green]Built features: {X.shape} -> {FEATURES / 'features.parquet'}[/green]")
    rprint(f"[dim]  labeled rows: {X['label_score'].notna().sum()}/{len(X)}[/dim]")
    rprint(f"[dim]  feature columns: {len(json.loads((FEATURES / 'feature_columns.json').read_text()))}[/dim]")


if __name__ == "__main__":
    build()
