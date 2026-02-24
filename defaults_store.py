from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
PRESET_DIR = BASE_DIR / "data" / "presets"


def ensure_dirs() -> None:
    PRESET_DIR.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "preset"


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


def default_preset_template() -> dict[str, Any]:
    return {
        "sims": 80,
        "steps_per_minute": 1,
        "seed": 42,
        "peak_hours": 3.5,
        "peak_pct": 0.58,
        "minutes_deviation": 22.0,
        "arrival_wave_strength": 0.22,
        "arrival_wave_frequency": 1.4,
        "event_start_min": 120.0,
        "event_duration_min": 45.0,
        "show_day_hours": 8.0,
        "main_event_days": 1,
        "event_multiplier": 1.35,
        "main_event_pull_chance": 0.55,
        "main_event_strength_multiplier": 7.5,
        "turnback_rate": 0.42,
        "forward_bias": 1.6,
        "congestion_alpha": 0.2,
        "goal_bias": 2.4,
        "attractor_pull_chance": 0.32,
        "pull_check_every_n_steps": 4,
        "attractor_cooldown_steps": 8,
        "pct_wanderer": 0.48,
        "pct_mission": 0.16,
        "pct_explorer": 0.12,
        "pct_main": 0.24,
        "group_prob_solo": 0.52,
        "group_prob_couple": 0.34,
        "group_prob_triple": 0.10,
        "group_prob_quad": 0.04,
        "group_cohesion": 0.9,
        "memory_window_steps": 10,
        "repeat_edge_penalty": 0.7,
        "novelty_bonus_initial": 0.33,
        "novelty_decay_rate": 0.42,
        "pixels_per_10m": 180.0,
        "booth_capacity": 3,
        "booth_service_steps": 1,
        "booth_max_queue_wait_steps": 28,
        "main_loyal_multiplier": 1.9,
        "explorer_novelty_bias": 0.1,
        "heatmap_defaults": {
            "show_edges": True,
            "show_nodes": True,
            "intensity": 0.9,
            "max_w": 12,
        },
    }


def list_presets() -> list[str]:
    ensure_dirs()
    return sorted([p.stem for p in PRESET_DIR.glob("*.json")])


def load_preset(preset_id: str) -> dict[str, Any]:
    ensure_dirs()
    path = PRESET_DIR / f"{preset_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {preset_id}")
    return _read_json_file(path, f"Preset '{preset_id}'")


def save_preset(name: str, payload: dict[str, Any]) -> str:
    ensure_dirs()
    preset_id = slugify(name)
    path = PRESET_DIR / f"{preset_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return preset_id


def delete_preset(preset_id: str) -> None:
    ensure_dirs()
    path = PRESET_DIR / f"{preset_id}.json"
    if path.exists():
        path.unlink()
