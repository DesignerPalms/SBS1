from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SIM_RUNS_DIR = BASE_DIR / "data" / "sim_runs"
SIM_IMAGES_DIR = SIM_RUNS_DIR / "images"


def ensure_dirs() -> None:
    SIM_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SIM_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "sim-run"


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"{label} is empty (empty response).")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{label} has invalid JSON: {e.msg} at line {e.lineno}, col {e.colno}.") from e
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return data


def list_sim_runs() -> list[str]:
    ensure_dirs()
    return sorted([p.stem for p in SIM_RUNS_DIR.glob("*.json")])


def save_sim_run(name: str, payload: dict[str, Any]) -> str:
    ensure_dirs()
    run_id = slugify(name)
    path = SIM_RUNS_DIR / f"{run_id}.json"
    payload = dict(payload)
    payload.setdefault("meta", {})
    payload["meta"]["saved_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return run_id


def load_sim_run(run_id: str) -> dict[str, Any]:
    ensure_dirs()
    path = SIM_RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Sim run not found: {run_id}")
    return _read_json_file(path, f"Saved sim '{run_id}'")


def delete_sim_run(run_id: str) -> None:
    ensure_dirs()
    run = load_sim_run(run_id)
    for key in ("peak_heatmap_image", "off_heatmap_image"):
        img = run.get("artifacts", {}).get(key)
        if img:
            p = SIM_IMAGES_DIR / img
            if p.exists():
                p.unlink()
    path = SIM_RUNS_DIR / f"{run_id}.json"
    if path.exists():
        path.unlink()
