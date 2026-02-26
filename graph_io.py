from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LAYOUT_DIR = DATA_DIR / "layouts"
IMAGE_DIR = DATA_DIR / "images"


def ensure_dirs() -> None:
    LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "layout"


def new_layout_template(name: str = "Untitled Layout") -> dict[str, Any]:
    return {
        "meta": {
            "name": name,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        },
        "image": {"filename": None},
        "nodes": [],
        "edges": [],
        "booths": [],
        "entrances": [],
        "attractors": [],
    }


def list_layouts() -> list[str]:
    ensure_dirs()
    return sorted([p.stem for p in LAYOUT_DIR.glob("*.json")])


def load_layout(layout_id: str) -> dict[str, Any]:
    ensure_dirs()
    path = LAYOUT_DIR / f"{layout_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Layout not found: {layout_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_layout(layout: dict[str, Any], layout_id: str | None = None) -> str:
    ensure_dirs()
    if layout_id is None:
        base = slugify(layout.get("meta", {}).get("name", "layout"))
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        layout_id = f"{base}-{stamp}"

    layout.setdefault("meta", {})
    layout["meta"]["updated_at"] = datetime.utcnow().isoformat()
    path = LAYOUT_DIR / f"{layout_id}.json"
    path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    return layout_id


def delete_layout(layout_id: str) -> None:
    ensure_dirs()
    layout = load_layout(layout_id)
    image_name = layout.get("image", {}).get("filename")
    if image_name:
        image_path = IMAGE_DIR / image_name
        if image_path.exists():
            image_path.unlink()
    path = LAYOUT_DIR / f"{layout_id}.json"
    if path.exists():
        path.unlink()
