from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any

from rich import print as rprint

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
NORMALIZED = DATA / "normalized"
FEATURES = DATA / "features"
MODELS = DATA / "models"
PREDICTIONS = DATA / "predictions"

for p in [DATA, RAW, NORMALIZED, FEATURES, MODELS, PREDICTIONS]:
    p.mkdir(parents=True, exist_ok=True)


def save_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def safe_stem(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)