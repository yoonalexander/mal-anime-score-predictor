#!/usr/bin/env bash
# Full end-to-end pipeline: ingest -> features -> train -> predict -> export.
# Run from the repository root on a fresh clone.
#
# This re-fetches seasonal data from Jikan (with AniList fallback), respects
# rate limits, and regenerates the committed frontend prediction JSON.
#
# Usage:
#   bash scripts/reproduce.sh            # full re-ingest + retrain
#   bash scripts/reproduce.sh --cache    # reuse cached raw payloads where present
set -euo pipefail

USE_CACHE=""
if [[ "${1:-}" == "--cache" ]]; then
  USE_CACHE="--use-cache"
fi

echo "== 1. Ingest historical seasons (2018-2025) =="
python -m src.ingest --start-year 2018 --end-year 2025 --seasons winter spring summer fall $USE_CACHE

echo "== 2. Build features =="
python -m src.features.build_features

echo "== 3. Train model (compares RF / HistGBR / Ridge / LightGBM) =="
python -m src.models.train

echo "== 4. Predict Summer 2026 + Fall 2025 =="
python -m src.models.predict --season 2026:summer
python -m src.models.predict --season 2025:fall --no-fetch

echo "== 5. Export predictions to frontend JSON =="
python -m src.export_predictions

echo "== Done. Frontend JSON is in anime-frontend/public/predictions/ =="
