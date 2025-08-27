# 🧰 Prereqs

* Windows 10/11
* **Anaconda** (or **Miniconda**) installed at `C:\Users\<you>\anaconda3`
* Your repo checked out, e.g. `C:\Users\alexy\Documents\Project 2025++\mal-anime-score-predictor`

---

# 1) Create & activate the environment (PowerShell)

Open **PowerShell** (Start → type “PowerShell” → Enter):

```powershell
# 1) Create a clean env (name: sparktts)
conda create -y -n sparktts python=3.10

# 2) Activate it
conda activate sparktts

# 3) Install build tools (needed by some wheels)
python -m pip install --upgrade pip wheel setuptools
```

### Install project dependencies

If your repo has `requirements.txt`, do:

```powershell
python -m pip install -r requirements.txt
```

If you **don’t** have it (or it’s incomplete), this minimal set works with what we built:

```powershell
python -m pip install pandas numpy "pyarrow>=15" fastparquet \
  scikit-learn joblib requests python-dotenv rich fastapi uvicorn
```

> Tip: if `fastparquet` complains about C++ Build Tools, you can skip it; `pyarrow` alone is fine for parquet IO.

---

# 2) Prepare the project

From the **repo root**:

```powershell
# Make sure the data folders exist
mkdir data\normalized -Force | Out-Null
mkdir data\features   -Force | Out-Null
mkdir data\models     -Force | Out-Null
mkdir data\predictions -Force | Out-Null
```

Create a **`.env`** file in the repo root (optional, but helpful):

```
TRAIN_START_YEAR=2012
TRAIN_END_YEAR=2024
TEST_YEAR=2099            # disables holding out a test season during iteration
JIKAN_COOLDOWN=1.8        # be gentle to the API
JIKAN_READ_TIMEOUT=90
```

---

# 3) Ingest data

### 3.1 Ingest **training history** (2012–2024)

```powershell
python -m src.ingest --start-year 2012 --end-year 2024 --seasons winter spring summer fall
```

This writes `data/normalized/anime.parquet` (appending, not overwriting).

### 3.2 Ingest **target season** (Fall 2025)

```powershell
python -m src.ingest --start-year 2025 --end-year 2025 --seasons fall
```

> You can re-run either command any time; our `ingest.py` appends and dedupes by `mal_id`.

---

# 4) Fetch labels (scores) for the training years

This step calls Jikan’s **details** endpoint to get final scores for past anime. Do it in chunks so it doesn’t feel slow:

```powershell
# Most recent years first (quick payoff)
python -m src.ingest_details --year-min 2023 --year-max 2024

# Then expand training data
python -m src.ingest_details --year-min 2018 --year-max 2022

# (Optional) add older years if you want even more data
python -m src.ingest_details --year-max 2017
```

This writes/updates `data/normalized/labels.parquet`.
It’s **resumable** — re-running will skip already labeled IDs & cached details.

---

# 5) Build features

```powershell
python -m src.features.build_features
```

You’ll see something like:

```
Built features: (14572, 40) -> data/features/features.parquet
Labeled rows: 9892/14572
```

---

# 6) Train the model

```powershell
python -m src.models.train
```

Outputs:

* `data/models/rf_model.joblib`
* `data/models/model_columns.json` (used by predict for column alignment)

You’ll see MAE/RMSE for Train/Val.

---

# 7) Predict for Fall 2025

```powershell
python -m src.models.predict --season 2025:fall
```

Outputs:

* `data/predictions/predictions_2025_fall.parquet`

(Our `predict.py` auto-aligns feature columns to what the model expects and filters to “upcoming/not yet aired” when possible.)

Optional: view top 10 in the console:

```powershell
python - << 'PY'
import pandas as pd
df = pd.read_parquet("data/predictions/predictions_2025_fall.parquet")
print(df.sort_values("pred_score", ascending=False).head(10).to_string(index=False))
PY
```

---

# 8) Serve the API (optional)

```powershell
uvicorn src.serving.app:app --reload --port 8000
```

Open:

```
http://127.0.0.1:8000/season/2025/fall/predictions
```

---

# 9) (Optional) Quick status checker

We added `src/utils/status.py`. It tells you what exists and what to run next:

```powershell
python -m src.utils.status --season 2025:fall
```

---

## One-liner “do what’s missing” (Windows runner)

If you saved the `run.bat` I gave you earlier in repo root:

```powershell
# uses your sparktts env path built into run.bat
.\run.bat pipeline 2025:fall
```

This will:

* ingest history if missing,
* append Fall 2025,
* fetch labels if missing (recent first),
* build features,
* train if no model,
* predict Fall 2025.

---

## Troubleshooting (super common on Windows)

**NumPy 2.x vs 1.x mismatch**

* Always run in your **sparktts** env (`conda activate sparktts`).
* If you see “compiled against NumPy 1.x” errors, reinstall in this env:

  ```powershell
  python -m pip install --upgrade numpy pandas pyarrow
  ```

**Git Bash won’t activate conda**

* Prefer **PowerShell** for conda usage.
* If you *must* use Git Bash, add this to `~/.bashrc`:

  ```bash
  export _CONDA_EXE=/c/Users/alexy/anaconda3/Scripts/conda.exe
  export CONDA_EXE=/c/Users/alexy/anaconda3/Scripts/conda.exe
  source /c/Users/alexy/anaconda3/etc/profile.d/conda.sh
  ```

  Then open a new Git Bash → `conda activate sparktts`.

**Bypass activation entirely**

* You can always run with the env’s Python directly:

  ```powershell
  "C:\Users\alexy\anaconda3\envs\sparktts\python.exe" -m src.models.predict --season 2025:fall
  ```

---

## TL;DR cheatsheet

```powershell
# PowerShell
conda create -y -n sparktts python=3.10
conda activate sparktts
python -m pip install -r requirements.txt   # or the minimal list above

python -m src.ingest --start-year 2012 --end-year 2024 --seasons winter spring summer fall
python -m src.ingest --start-year 2025 --end-year 2025 --seasons fall
python -m src.ingest_details --year-min 2023 --year-max 2024
python -m src.ingest_details --year-min 2018 --year-max 2022
python -m src.features.build_features
python -m src.models.train
python -m src.models.predict --season 2025:fall
uvicorn src.serving.app:app --reload
```
