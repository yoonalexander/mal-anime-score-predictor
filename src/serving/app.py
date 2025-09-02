from __future__ import annotations
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..utils.io import PREDICTIONS

app = FastAPI(title="MAL Score Predictor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/season/{year}/{season}/predictions")
async def season_predictions(year: int, season: str):
    path = PREDICTIONS / f"predictions_{year}_{season.lower()}.parquet"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Predictions not found. Run prediction step first.")
    df = pd.read_parquet(path)

    # handle optional image column(s)
    image_col = next((c for c in ["image_url","cover_url","poster_url"] if c in df.columns), None)

    return [
        {
            "mal_id": int(row.mal_id),
            "title": row.title,
            "year": int(row.year),
            "season": str(row.season),
            "pred_score": float(row.pred_score),
            "image_url": (getattr(row, image_col) if image_col else None),
        }
        for row in df.itertuples(index=False)
    ]
