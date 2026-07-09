# Full end-to-end pipeline: ingest -> features -> train -> predict -> export.
# Run from the repository root on a fresh clone (Windows PowerShell).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -UseCache
param(
  [switch]$UseCache
)

$cacheFlag = if ($UseCache) { "--use-cache" } else { "" }

Write-Host "== 1. Ingest historical seasons (2018-2025) =="
python -m src.ingest --start-year 2018 --end-year 2025 --seasons winter spring summer fall $cacheFlag
if ($LASTEXITCODE -ne 0) { throw "ingest failed" }

Write-Host "== 2. Build features =="
python -m src.features.build_features
if ($LASTEXITCODE -ne 0) { throw "build_features failed" }

Write-Host "== 3. Train model =="
python -m src.models.train
if ($LASTEXITCODE -ne 0) { throw "train failed" }

Write-Host "== 4. Predict Summer 2026 + Fall 2025 =="
python -m src.models.predict --season 2026:summer
if ($LASTEXITCODE -ne 0) { throw "predict 2026:summer failed" }
python -m src.models.predict --season 2025:fall --no-fetch
if ($LASTEXITCODE -ne 0) { throw "predict 2025:fall failed" }

Write-Host "== 5. Export predictions to frontend JSON =="
python -m src.export_predictions
if ($LASTEXITCODE -ne 0) { throw "export failed" }

Write-Host "== Done. Frontend JSON is in anime-frontend/public/predictions/ =="
