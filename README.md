# MAL Anime Score Predictor

Predicts MyAnimeList anime scores from seasonal metadata (Jikan/AniList), trains a
leakage-safe regression model, and serves the predictions on a static website
deployed via Vercel.

The production website needs **no backend**: it reads committed prediction JSON
from `anime-frontend/public/predictions/`. The Python pipeline regenerates that
JSON on demand.

## Features

- Ingest seasonal anime data from the Jikan API, with an AniList GraphQL
  fallback (used when Jikan's season endpoints are unavailable).
- Capture cover image URLs, studios, genres, themes, demographics, and more.
- Cache raw API responses per season to avoid re-hitting rate limits on re-runs.
- Build leakage-safe features from metadata knowable before a season airs
  (studio, genres, themes, source, type, episodes, season, year…).
- Train and compare multiple models (Random Forest, HistGradientBoosting,
  Ridge, LightGBM) with a strict chronological train/val/test split.
- Generate predictions with an uncertainty band.
- Export a lightweight, frontend-ready JSON artifact (the only data shipped to
  the deployed site).
- React + Vite frontend that loads the static JSON — search, sort, season
  switcher, synopsis, and CSV export.

## Project Structure

```text
.
|-- anime-frontend/                 # React + Vite prediction browser
|   |-- public/predictions/*.json   # <-- committed static predictions (ships to Vercel)
|   `-- src/                        # app code
|-- data/                           # generated locally (gitignored): raw/normalized/features/models/predictions
|-- scripts/reproduce.{sh,ps1}      # one-shot full pipeline
|-- src/
|   |-- features/build_features.py  # feature engineering
|   |-- ingest.py                   # Jikan/AniList ingest + normalization
|   |-- export_predictions.py       # parquet -> frontend JSON
|   |-- mal/client.py               # Jikan + AniList client
|   |-- models/{train,predict}.py   # training + prediction
|   `-- serving/app.py              # optional FastAPI (local dev only)
|-- requirements.txt
`-- vercel.json
```

`data/` is gitignored (large datasets/models/predictions). Only the lightweight
frontend JSON under `anime-frontend/public/predictions/` is committed.

## Requirements

- Python 3.11+ (3.14 tested)
- Node.js 20+ (24 tested), npm

## Quick Start (Frontend Only)

If you only want to run/preview the website, you do **not** need the Python
pipeline — the prediction JSON is already committed.

```bash
cd anime-frontend
npm install
npm run dev      # http://localhost:5173
```

To preview the production build:

```bash
npm run build
npm run preview
```

No environment variables are required.

## Full ML Pipeline (Fresh Clone)

### 1. Backend setup

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. One-shot pipeline

```bash
# macOS/Linux:
bash scripts/reproduce.sh            # full re-ingest + retrain
bash scripts/reproduce.sh --cache    # reuse cached raw payloads where present

# Windows PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1
```

This runs: ingest → build_features → train → predict → export_predictions.

### 3. Step-by-step (manual)

```bash
# Ingest historical seasons (Jikan first, AniList fallback). Respects rate limits.
python -m src.ingest --start-year 2018 --end-year 2025 --seasons winter spring summer fall
# Add the --use-cache flag to reuse locally cached raw payloads.

# Build features
python -m src.features.build_features

# Train (compares RF / HistGBR / Ridge / LightGBM, picks best by val MAE)
python -m src.models.train

# Predict a season (auto-fetches it if missing locally)
python -m src.models.predict --season 2026:summer
python -m src.models.predict --season 2025:fall --no-fetch

# Export prediction parquets -> committed frontend JSON
python -m src.export_predictions
```

### Configuration (`.env`)

```env
JIKAN_COOLDOWN=1.2
DEFAULT_SEASONS=winter,spring,summer,fall
INGEST_SOURCE=auto
TRAIN_START_YEAR=2018
TRAIN_END_YEAR=2023
VAL_YEAR=2024
TEST_YEAR=2025
```

No MAL API key is required.

## Deploy to Vercel

The site is a static Vite build. The root `vercel.json` builds from
`anime-frontend/` and serves `anime-frontend/dist/`. The committed prediction
JSON under `anime-frontend/public/predictions/` is copied into the build output
by Vite automatically.

```bash
npm install -g vercel   # once
vercel                  # preview deploy
vercel --prod           # production
```

No environment variables, no backend, no build-time API calls. A fresh clone
deploys correctly.

## Data Pipeline Details

### Jikan + AniList

`src/ingest.py` prefers Jikan (canonical MAL data). Jikan's season endpoints are
occasionally unavailable (HTTP 504 due to upstream MAL issues); in that case the
pipeline transparently falls back to AniList, which returns the same core
metadata **plus** cover images on a public CDN. Raw payloads are cached under
`data/raw/<year>_<season>/season_<source>.json` so re-runs are fast and polite
to the APIs.

### Leakage-safe modeling

The label is the MAL score. Features are restricted to fields available
**before** a season airs:

- Studio, genres, themes, demographics, source, type, rating
- Episode count (announced), season, year
- Title/synopsis length, sequel-signal in the title

`members`, `favorites`, `popularity`, and `rank` are **excluded** as features
because they reflect post-airing audience size and would leak the target. The
split is chronological (train ≤ 2023, validate = 2024, test = 2025) to mirror the
real prediction task. See the "Model evaluation" section in
`data/models/metrics.json` after training.

## Optional: Local FastAPI Backend

A FastAPI app is included for local experimentation but is **not** used in
production (the static JSON replaces it).

```bash
uvicorn src.serving.app:app --reload
# GET http://127.0.0.1:8000/season/2025/fall/predictions
```

If you want to serve predictions live, update `allow_origins` in
`src/serving/app.py` and point the (legacy) `VITE_API_BASE_URL` at it.

## Useful Commands

```bash
# Backend
python -m src.ingest --start-year 2018 --end-year 2025 --seasons winter spring summer fall --use-cache
python -m src.features.build_features
python -m src.models.train
python -m src.models.predict --season 2026:summer
python -m src.export_predictions
python -m src.utils.status

# Frontend
cd anime-frontend
npm run dev
npm run build
npm run lint
```

## Notes and Limitations

- The model predicts from metadata only. MAL scores are crowd-sourced, so a
  metadata-only model has a practical MAE floor around 0.6 on held-out seasons.
- Jikan season endpoints can be intermittently unavailable; AniList is the
  automatic fallback and provides cover images.
- Heavy training data and model artifacts stay gitignored/local. Only the
  lightweight frontend prediction JSON is committed.
- Cover images come from AniList/Jikan CDNs (public, production-safe).

## Additional Documentation

- `design_doc.md` — original project design.
- `user_manual.md` — user-facing instructions.
