from __future__ import annotations

from typing import Any

from PIL import Image, ImageColor, ImageDraw


PALETTE = ["#2c7bb6", "#00a6ca", "#00ccbc", "#90eb9d", "#ffff8c", "#f9d057", "#f29e2e", "#e76818", "#d7191c"]


def _norm_values(values: dict[Any, float], mode: str, bins: int = 5) -> dict[Any, float]:
    if not values:
        return {}
    if mode == "value":
        max_v = max(values.values()) or 1.0
        return {k: v / max_v for k, v in values.items()}

    sorted_items = sorted(values.items(), key=lambda x: x[1])
    out = {}
    if mode == "percentile":
        n = max(1, len(sorted_items) - 1)
        for i, (k, _v) in enumerate(sorted_items):
            out[k] = i / n
        return out

    # rank_bins
    bins = max(3, min(9, bins))
    n = len(sorted_items)
    for i, (k, _v) in enumerate(sorted_items):
        b = int((i / max(1, n - 1)) * (bins - 1))
        out[k] = b / max(1, bins - 1)
    return out


def _pick_color(norm: float) -> tuple[int, int, int, int]:
    idx = int(norm * (len(PALETTE) - 1))
    rgb = ImageColor.getrgb(PALETTE[idx])
    return (rgb[0], rgb[1], rgb[2], 180)


def draw_heatmap_overlay(
    layout: dict[str, Any],
    base_image: Image.Image,
    node_values: dict[str, float],
    edge_values: dict[str, float],
    mode: str = "rank_bins",
    bins: int = 5,
    show_edges: bool = True,
    show_nodes: bool = True,
    intensity: float = 0.9,
    max_w: int = 12,
) -> Image.Image:
    img = base_image.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    nodes = {n["id"]: n for n in layout.get("nodes", [])}

    node_norm = _norm_values({int(k): float(v) for k, v in node_values.items()}, mode, bins)
    edge_parsed = {}
    for k, v in edge_values.items():
        a, b = k.split("-")
        edge_parsed[(int(a), int(b))] = float(v)
    edge_norm = _norm_values(edge_parsed, mode, bins)

    if show_edges:
        for e in layout.get("edges", []):
            key = tuple(sorted((e["source"], e["target"])))
            if key not in edge_norm:
                continue
            n1 = nodes.get(e["source"])
            n2 = nodes.get(e["target"])
            if not n1 or not n2:
                continue
            norm = edge_norm[key]
            color = _pick_color(norm)
            width = max(1, int(1 + norm * max_w * intensity))
            draw.line((n1["x"], n1["y"], n2["x"], n2["y"]), fill=color, width=width)

    if show_nodes:
        r = 8
        for nid, n in nodes.items():
            if nid not in node_norm:
                continue
            norm = node_norm[nid]
            color = _pick_color(norm)
            draw.ellipse((n["x"] - r, n["y"] - r, n["x"] + r, n["y"] + r), fill=color, outline=(0, 0, 0, 255), width=1)

    return Image.alpha_composite(img, overlay).convert("RGB")
