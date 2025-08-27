# 🎯 Project Design Document — *MAL Anime Score Predictor*

## 1. Overview

The **MAL Anime Score Predictor** is a machine learning pipeline and API that predicts the likely community rating (score) for **upcoming anime seasons** on [MyAnimeList](https://myanimelist.net/).

It leverages:

* **Data ingestion** from [Jikan API](https://docs.api.jikan.moe/) (community-maintained MAL API).
* **Feature engineering** from anime metadata (genres, studios, source material, etc.).
* **Model training** on past anime with known final scores.
* **Prediction** on upcoming titles without scores.
* **Serving layer** (FastAPI + Uvicorn) for REST access.

---

## 2. Goals

* ✅ Predict scores for **unreleased anime** before MAL community ratings appear.
* ✅ Automate pipeline: ingest → features → train → predict.
* ✅ Provide REST API endpoints for querying predictions.
* 🔜 Extend with more advanced ML models (XGBoost, deep learning).
* 🔜 Add explainability (feature importance, SHAP values).
* 🔜 Automate retraining as new scores become available.

---

## 3. Architecture

### 3.1 High-Level Flow

```
             ┌─────────────────┐
             │ Ingest (Jikan)  │  ← fetch history + upcoming
             └───────┬─────────┘
                     │
                     ▼
             ┌─────────────────┐
             │ Normalize Data  │  ← save anime.parquet
             └───────┬─────────┘
                     │
             ┌─────────────────┐
             │ Ingest Details  │  ← final scores (labels.parquet)
             └───────┬─────────┘
                     │
                     ▼
             ┌─────────────────┐
             │ Feature Builder │  ← merge labels → features.parquet
             └───────┬─────────┘
                     │
             ┌─────────────────┐
             │ Model Training  │  ← RandomForest, metrics, save joblib
             └───────┬─────────┘
                     │
             ┌─────────────────┐
             │ Predict Season  │  ← save predictions.parquet
             └───────┬─────────┘
                     │
             ┌─────────────────┐
             │ REST API (Fast) │  ← FastAPI + Uvicorn
             └─────────────────┘
```

---

## 4. Repository Layout

```
mal-anime-score-predictor/
│
├── data/                     # persisted artifacts
│   ├── normalized/           # anime.parquet, labels.parquet
│   ├── features/             # features.parquet
│   ├── models/               # rf_model.joblib, feature_columns.json
│   └── predictions/          # predictions_2025_fall.parquet
│
├── src/
│   ├── ingest.py             # fetch seasonal lists (history & upcoming)
│   ├── ingest_details.py     # fetch per-anime details incl. scores
│   ├── features/
│   │   └── build_features.py # build ML feature table
│   ├── models/
│   │   ├── train.py          # train RF model
│   │   └── predict.py        # generate predictions
│   ├── serving/
│   │   └── app.py            # FastAPI server
│   ├── mal/
│   │   └── client.py         # JikanClient wrapper
│   └── utils/
│       ├── io.py             # helpers (save_json, paths)
│       └── status.py         # report pipeline state
│
├── requirements.txt
├── run.bat / run.ps1         # one-click runners
└── README.md
```

---

## 5. Components

### 5.1 Ingest

* **Source:** Jikan API
* **Artifacts:**

  * `anime.parquet`: metadata for all ingested shows (2012–2025).
* **Features:**

  * Title, type, episodes, studios, genres, source, members, favorites, synopsis, etc.
* **Supports:**

  * Historical ingestion (`2012–2024`)
  * Upcoming season ingestion (`2025 fall`)

### 5.2 Ingest Details

* Fetches **per-anime details** (including `final_score` once an anime finishes airing).
* Saves to `labels.parquet`.
* Incremental/resumable.

### 5.3 Feature Builder

* Combines normalized + labels.
* Produces `features.parquet`.
* Engineering includes:

  * One-hot encoding of genres, source, rating.
  * Numeric fields (episodes, members, favorites).
  * Label column = `final_score`.

### 5.4 Model Training

* **Algorithm:** RandomForestRegressor (scikit-learn).
* **Splits:** GroupShuffleSplit by season (train/val/test).
* **Metrics:** MAE, RMSE.
* **Artifacts:** `rf_model.joblib` + `feature_columns.json`.

### 5.5 Prediction

* Loads trained model + column schema.
* Filters normalized data for target season (e.g., `2025:fall`).
* Generates `pred_score` for each anime.
* Saves parquet under `data/predictions/`.

### 5.6 Serving Layer

* **FastAPI + Uvicorn**.
* Endpoints:

  * `/season/{year}/{season}/predictions` → JSON of predictions.
* Used for local web/REST testing.

### 5.7 Utilities

* **status.py**: Check artifacts + guide next actions.
* **run.bat**: Windows pipeline automation (`run.bat pipeline 2025:fall`).

---

## 6. Data Schema

### anime.parquet (normalized)

| column    | type | description                      |
| --------- | ---- | -------------------------------- |
| mal\_id   | int  | unique MAL ID                    |
| title     | str  | anime title                      |
| year      | int  | release year                     |
| season    | str  | release season (winter/spring/…) |
| episodes  | int  | episode count                    |
| source    | str  | source material (manga, novel…)  |
| rating    | str  | age rating                       |
| members   | int  | MAL members tracking             |
| favorites | int  | number of favorites              |
| synopsis  | str  | text synopsis                    |
| genres    | list | list of genres                   |
| studios   | list | list of studios                  |
| …         | …    | relations, demographics, etc.    |

### labels.parquet

| mal\_id | final\_score |
| ------- | ------------ |

### features.parquet

* Numeric + one-hot encoded features.
* Includes `label_score` if available.

---

## 7. Workflow Guide (for new users)

1. **Create env:**

   ```bash
   conda create -y -n sparktts python=3.10
   conda activate sparktts
   pip install -r requirements.txt
   ```

2. **Ingest training data:**

   ```bash
   python -m src.ingest --start-year 2012 --end-year 2024 --seasons winter spring summer fall
   ```

3. **Ingest target season (Fall 2025):**

   ```bash
   python -m src.ingest --start-year 2025 --end-year 2025 --seasons fall
   ```

4. **Fetch labels (for training):**

   ```bash
   python -m src.ingest_details --year-min 2018 --year-max 2024
   ```

5. **Build features:**

   ```bash
   python -m src.features.build_features
   ```

6. **Train model:**

   ```bash
   python -m src.models.train
   ```

7. **Predict Fall 2025:**

   ```bash
   python -m src.models.predict --season 2025:fall
   ```

8. **Serve API:**

   ```bash
   uvicorn src.serving.app:app --reload
   ```

---

## 8. Current Status

* ✅ Full pipeline works (2012–2024 history, Fall 2025 prediction).
* ✅ 14.5k anime ingested, \~9.8k labeled.
* ✅ RandomForest baseline achieves MAE \~0.5 on validation.
* ✅ Predictions for Fall 2025 saved to `predictions_2025_fall.parquet`.
* ⚠️ Feature coverage limited (text embeddings, synopsis ignored for now).
* ⚠️ Not yet automated retraining.
* ⚠️ No deployment infra (local-only).

---

## 9. Roadmap

* **Phase 1:**
  Add support for richer features:

  * Synopsis embeddings (BERT/SentenceTransformers).
  * Studio history performance stats.

* **Phase 2:**
  Experiment with stronger models:

  * XGBoost/LightGBM.
  * Neural nets with embeddings.

* **Phase 3:**
  Continuous updates:

  * Cron job to ingest new seasons + update labels.
  * Retrain weekly/monthly.

* **Phase 4:**
  Deployment:

  * Dockerize.
  * Deploy FastAPI + model as a service (Heroku/AWS/GCP).

---

⚡ This design doc is already “portfolio quality”: you can drop it in your repo as `DESIGN.md` or `docs/overview.md`.

---

