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


def default_preset_template() -> dict[str, Any]:
    return {
        "sims": 50,
        "steps_per_minute": 1,
        "seed": 42,
        "peak_hours": 4.0,
        "peak_pct": 0.6,
        "minutes_deviation": 30.0,
        "arrival_wave_strength": 0.15,
        "arrival_wave_frequency": 2.0,
        "event_start_min": 120.0,
        "event_duration_min": 30.0,
        "event_multiplier": 1.2,
        "turnback_rate": 0.3,
        "congestion_alpha": 0.1,
        "goal_bias": 2.0,
        "attractor_pull_chance": 0.25,
        "pull_check_every_n_steps": 5,
        "attractor_cooldown_steps": 10,
        "pct_wanderer": 0.4,
        "pct_mission": 0.2,
        "pct_explorer": 0.2,
        "pct_main": 0.2,
        "couples_rate": 0.2,
        "group_prob_solo": 0.7,
        "group_prob_couple": 0.2,
        "group_prob_triple": 0.08,
        "group_prob_quad": 0.02,
        "group_cohesion": 0.9,
        "memory_window_steps": 8,
        "repeat_edge_penalty": 0.75,
        "novelty_bonus_initial": 0.4,
        "novelty_decay_rate": 0.35,
        "walk_speed_mean": 110.0,
        "walk_speed_std": 20.0,
        "booth_capacity": 2,
        "booth_service_steps": 1,
        "attractor_capacity": 2,
        "max_queue_wait_steps": 20,
        "main_loyal_multiplier": 1.7,
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
    return json.loads(path.read_text(encoding="utf-8"))


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
