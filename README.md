# MAL Anime Score Predictor — Starter

This repo fetches seasonal anime metadata from the Jikan API, builds simple tabular features, trains a baseline regression model to predict final MAL-like scores, and serves predictions via a FastAPI endpoint.

## Quickstart

```bash
# 1) clone & enter
# git clone <your-fork-url>
cd mal-anime-score-predictor

# 2) Python env
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

# 3) Install deps
pip install -r requirements.txt

# 4) Configure
cp .env.example .env
# edit .env if desired (rate limit, years, etc.)

# 5) Ingest historical seasons (ex: 2018–2024)
python -m src.ingest --start-year 2018 --end-year 2024 --seasons winter spring summer fall

# 6) Build features
python -m src.features.build_features

# 7) Train baseline model
python -m src.models.train

# 8) Predict for upcoming/next season (auto-detects next if not provided)
python -m src.models.predict --season auto

# 9) Serve predictions API
uvicorn src.serving.app:app --reload
# Visit: http://127.0.0.1:8000/season/<YEAR>/<SEASON>/predictions