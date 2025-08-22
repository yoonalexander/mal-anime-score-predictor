from __future__ import annotations
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

from ..utils.io import PREDICTIONS

app = FastAPI(title="MAL Score Predictor")


@app.get("/season/{year}/{season}/predictions")
async def season_predictions(year: int, season: str):
    path = PREDICTIONS / f"predictions_{year}_{season.lower()}.parquet"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Predictions not found. Run prediction step first.")
    df = pd.read_parquet(path)
    # convert to friendly JSON
    return [
        {
            "mal_id": int(row.mal_id),
            "title": row.title,
            "year": int(row.year),
            "season": str(row.season),
            "pred_score": float(row.pred_score),
        }
        for row in df.itertuples(index=False)
    ]