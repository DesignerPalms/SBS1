from __future__ import annotations

from datetime import datetime
import time
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from graph_io import IMAGE_DIR, delete_layout, list_layouts, load_layout, new_layout_template, save_layout, slugify


def _safe_image_name(layout_name: str, original: str) -> str:
    ext = Path(original).suffix.lower() or ".png"
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{slugify(layout_name)}-{stamp}{ext}"


def _draw_preview(layout: dict[str, Any]) -> Image.Image:
    img_name = layout.get("image", {}).get("filename")
    if img_name and (IMAGE_DIR / img_name).exists():
        img = Image.open(IMAGE_DIR / img_name).convert("RGB")
    else:
        img = Image.new("RGB", (900, 600), "#f4f4f4")

    draw = ImageDraw.Draw(img)
    nodes = {n["id"]: n for n in layout.get("nodes", [])}

    for e in layout.get("edges", []):
        n1, n2 = nodes.get(e["source"]), nodes.get(e["target"])
        if not n1 or not n2:
            continue
        width = 5 if e.get("is_main") else 2
        draw.line((n1["x"], n1["y"], n2["x"], n2["y"]), fill="#444", width=width)

    booth_nodes = {b["node_id"] for b in layout.get("booths", [])}
    entrance_nodes = {e["node_id"] for e in layout.get("entrances", [])}
    attractor_nodes = {a["node_id"] for a in layout.get("attractors", [])}
    selected_node = st.session_state.get("builder_selected_node")

    for nid, n in nodes.items():
        x, y = n["x"], n["y"]
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#111")
        draw.text((x + 8, y - 10), str(nid), fill="#111")
        if nid in booth_nodes:
            draw.ellipse((x - 11, y - 11, x + 11, y + 11), outline="blue", width=2)
        if nid in entrance_nodes:
            draw.ellipse((x - 14, y - 14, x + 14, y + 14), outline="green", width=2)
        if nid in attractor_nodes:
            draw.polygon([(x, y - 14), (x - 12, y + 10), (x + 12, y + 10)], outline="yellow", width=2)
        if selected_node == nid:
            draw.ellipse((x - 18, y - 18, x + 18, y + 18), outline="#ff4b4b", width=3)

    return img


def _draw_scale_key(img: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(img)
    px_len = int(st.session_state.get("builder_scale_px", 120))
    dist_val = float(st.session_state.get("builder_scale_distance", 10.0))
    dist_unit = st.session_state.get("builder_scale_unit", "m")
    walk_speed = float(st.session_state.get("builder_scale_walk_speed", 80.0))

    px_len = max(20, min(px_len, img.width - 80))
    x1 = 30
    y1 = max(30, img.height - 30)
    x2 = x1 + px_len

    draw.line((x1, y1, x2, y1), fill="#111", width=4)
    draw.line((x1, y1 - 8, x1, y1 + 8), fill="#111", width=3)
    draw.line((x2, y1 - 8, x2, y1 + 8), fill="#111", width=3)

    label = f"{dist_val:g} {dist_unit}"
    sec = None
    if walk_speed > 0:
        minutes = dist_val / walk_speed
        sec = int(round(minutes * 60))
    if sec is not None:
        label += f" (~{sec}s walk @ {walk_speed:g} {dist_unit}/min)"

    draw.rectangle((x1 - 4, y1 - 28, min(img.width - 5, x1 + 8 + len(label) * 7), y1 - 8), fill=(255, 255, 255))
    draw.text((x1, y1 - 26), label, fill="#111")
    return img


def _nearest_node_id(layout: dict[str, Any], x: int, y: int, radius: int = 20) -> int | None:
    best_id = None
    best_d2 = radius * radius
    for n in layout.get("nodes", []):
        dx = int(n["x"]) - x
        dy = int(n["y"]) - y
        d2 = dx * dx + dy * dy
        if d2 <= best_d2:
            best_d2 = d2
            best_id = int(n["id"])
    return best_id


def _distance2_point_to_segment(px: int, py: int, ax: int, ay: int, bx: int, by: int) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0:
        dx = px - ax
        dy = py - ay
        return float(dx * dx + dy * dy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    cx = ax + t * abx
    cy = ay + t * aby
    dx = px - cx
    dy = py - cy
    return float(dx * dx + dy * dy)


def _nearest_edge_index(layout: dict[str, Any], x: int, y: int, radius: int = 24) -> int | None:
    nodes = {n["id"]: n for n in layout.get("nodes", [])}
    best_idx = None
    best_d2 = float(radius * radius)
    for idx, e in enumerate(layout.get("edges", [])):
        n1 = nodes.get(e["source"])
        n2 = nodes.get(e["target"])
        if not n1 or not n2:
            continue
        d2 = _distance2_point_to_segment(x, y, int(n1["x"]), int(n1["y"]), int(n2["x"]), int(n2["y"]))
        if d2 <= best_d2:
            best_d2 = d2
            best_idx = idx
    return best_idx


def _reset_mode_selection_state() -> None:
    st.session_state.builder_connect_first_node = None
    st.session_state.builder_connect_last_sig = None
    st.session_state.builder_paint_last_sig = None
    st.session_state.builder_selected_node = None
    st.session_state.builder_select_last_sig = None
    st.session_state.builder_intersections_last_sig = None


def _handle_click_auto_add(layout: dict[str, Any], click: dict[str, Any] | None) -> None:
    if not click:
        return
    now = time.time()
    x, y = int(click["x"]), int(click["y"])
    click_sig = f"{x}:{y}"
    last_sig = st.session_state.get("builder_auto_last_sig")
    last_ts = float(st.session_state.get("builder_auto_last_ts", 0.0))
    cooldown_ok = (now - last_ts) >= 0.1
    if click_sig == last_sig or not cooldown_ok:
        return

    nid = 1 + max([n["id"] for n in layout.get("nodes", [])], default=0)
    layout["nodes"].append({"id": nid, "x": x, "y": y})
    st.session_state.builder_auto_last_sig = click_sig
    st.session_state.builder_auto_last_ts = now


def _handle_click_connect(layout: dict[str, Any], click: dict[str, Any] | None, make_main: bool) -> str | None:
    if not click:
        return None
    x, y = int(click["x"]), int(click["y"])
    click_sig = f"{x}:{y}"
    if st.session_state.get("builder_connect_last_sig") == click_sig:
        return None
    st.session_state.builder_connect_last_sig = click_sig

    nid = _nearest_node_id(layout, x, y)
    if nid is None:
        return "No node near click. Click closer to a node to connect."

    first = st.session_state.get("builder_connect_first_node")
    if first is None:
        st.session_state.builder_connect_first_node = nid
        return f"Selected node {nid}. Click another node to create an edge."

    if first == nid:
        return f"Node {nid} selected again. Click a different node."

    pair = tuple(sorted((int(first), nid)))
    existing = next((e for e in layout["edges"] if tuple(sorted((e["source"], e["target"]))) == pair), None)
    if existing:
        existing["is_main"] = existing.get("is_main", False) or make_main
        msg = f"Edge {pair[0]}-{pair[1]} already existed. Updated main={existing['is_main']}."
    else:
        layout["edges"].append({"source": pair[0], "target": pair[1], "is_main": bool(make_main)})
        msg = f"Added edge {pair[0]}-{pair[1]} (main={bool(make_main)})."

    st.session_state.builder_connect_first_node = None
    return msg


def _handle_click_paint_main(layout: dict[str, Any], click: dict[str, Any] | None) -> str | None:
    if not click:
        return None
    x, y = int(click["x"]), int(click["y"])
    click_sig = f"{x}:{y}"
    if st.session_state.get("builder_paint_last_sig") == click_sig:
        return None
    st.session_state.builder_paint_last_sig = click_sig

    idx = _nearest_edge_index(layout, x, y)
    if idx is None:
        return "No path near click. Click closer to an edge to mark it as main."

    edge = layout["edges"][idx]
    edge["is_main"] = True
    return f"Marked edge {edge['source']}-{edge['target']} as main."


def _handle_click_intersections(layout: dict[str, Any], click: dict[str, Any] | None, tolerance: int = 18) -> tuple[str | None, int]:
    if not click:
        return None, 0

    x, y = int(click["x"]), int(click["y"])
    click_sig = f"{x}:{y}"
    if st.session_state.get("builder_intersections_last_sig") == click_sig:
        return None, 0
    st.session_state.builder_intersections_last_sig = click_sig

    center_id = _nearest_node_id(layout, x, y, radius=max(20, tolerance + 6))
    if center_id is None:
        return "No node near click. Click closer to a node.", 0

    nodes = layout.get("nodes", [])
    center = next((n for n in nodes if n["id"] == center_id), None)
    if center is None:
        return "Selected node not found.", 0

    cx, cy = int(center["x"]), int(center["y"])
    best: dict[str, tuple[int, int]] = {}

    for n in nodes:
        nid = int(n["id"])
        if nid == center_id:
            continue
        nx, ny = int(n["x"]), int(n["y"])
        dx, dy = nx - cx, ny - cy

        if abs(dy) <= tolerance and dx > 0:
            cur = best.get("right")
            if cur is None or dx < cur[1]:
                best["right"] = (nid, dx)
        if abs(dy) <= tolerance and dx < 0:
            dist = abs(dx)
            cur = best.get("left")
            if cur is None or dist < cur[1]:
                best["left"] = (nid, dist)
        if abs(dx) <= tolerance and dy > 0:
            cur = best.get("down")
            if cur is None or dy < cur[1]:
                best["down"] = (nid, dy)
        if abs(dx) <= tolerance and dy < 0:
            dist = abs(dy)
            cur = best.get("up")
            if cur is None or dist < cur[1]:
                best["up"] = (nid, dist)

    added = 0
    for dir_name in ("left", "right", "up", "down"):
        hit = best.get(dir_name)
        if not hit:
            continue
        other = hit[0]
        pair = tuple(sorted((center_id, other)))
        existing = next((e for e in layout["edges"] if tuple(sorted((e["source"], e["target"]))) == pair), None)
        if existing is None:
            layout["edges"].append({"source": pair[0], "target": pair[1], "is_main": False})
            added += 1

    if added == 0:
        return f"Intersections: no new paths from node {center_id} (within tolerance {tolerance}px).", 0
    return f"Intersections: added {added} path(s) from node {center_id}.", added


def _handle_click_select(layout: dict[str, Any], click: dict[str, Any] | None) -> str | None:
    if not click:
        return None
    x, y = int(click["x"]), int(click["y"])
    click_sig = f"{x}:{y}"
    if st.session_state.get("builder_select_last_sig") == click_sig:
        return None
    st.session_state.builder_select_last_sig = click_sig

    nid = _nearest_node_id(layout, x, y)
    if nid is None:
        st.session_state.builder_selected_node = None
        return "No node near click. Selection cleared."

    st.session_state.builder_selected_node = nid
    return f"Selected node {nid}."


def _upsert_booth(layout: dict[str, Any], node_id: int, label: str) -> None:
    layout["booths"] = [b for b in layout["booths"] if b["node_id"] != node_id]
    layout["booths"].append({"node_id": node_id, "label": label or f"Booth {node_id}"})


def _upsert_entrance(layout: dict[str, Any], node_id: int, weight: float) -> None:
    layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != node_id]
    layout["entrances"].append({"node_id": node_id, "weight": float(weight)})


def _upsert_attractor(layout: dict[str, Any], node_id: int, label: str, attr_type: str, strength: float, draw_rate: float, dwell_steps: int, capacity: int, max_wait_steps: int) -> None:
    layout["attractors"] = [a for a in layout["attractors"] if a["node_id"] != node_id]
    layout["attractors"].append(
        {
            "node_id": node_id,
            "label": label or f"Attractor {node_id}",
            "type": attr_type,
            "strength": float(strength),
            "draw_rate": float(draw_rate),
            "dwell_steps": int(dwell_steps),
            "capacity": int(capacity),
            "max_wait_steps": int(max_wait_steps),
        }
    )


def _render_selected_node_editor(layout: dict[str, Any]) -> None:
    st.markdown("#### Selected Node Editor")
    node_id = st.session_state.get("builder_selected_node")
    if node_id is None:
        st.info("Click a node while in 'Select node' mode to edit it.")
        return

    node = next((n for n in layout.get("nodes", []) if n["id"] == node_id), None)
    if node is None:
        st.session_state.builder_selected_node = None
        st.info("Selected node no longer exists.")
        return

    st.write(f"Editing node **{node_id}**")

    # Ensure coordinate inputs are re-seeded when selection changes.
    if st.session_state.get("builder_selected_editor_node") != node_id:
        st.session_state.builder_selected_editor_node = node_id
        st.session_state.builder_selected_x = int(node["x"])
        st.session_state.builder_selected_y = int(node["y"])

    node["x"] = int(st.number_input("Node X", min_value=0, value=int(st.session_state.get("builder_selected_x", node["x"])), key="builder_selected_x"))
    node["y"] = int(st.number_input("Node Y", min_value=0, value=int(st.session_state.get("builder_selected_y", node["y"])), key="builder_selected_y"))

    existing_booth = next((b for b in layout["booths"] if b["node_id"] == node_id), None)
    existing_entrance = next((e for e in layout["entrances"] if e["node_id"] == node_id), None)
    existing_attractor = next((a for a in layout["attractors"] if a["node_id"] == node_id), None)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Booth**")
        booth_label = st.text_input("Booth label", value=(existing_booth or {}).get("label", f"Booth {node_id}"), key="builder_selected_booth_label")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Set booth", key="builder_selected_set_booth"):
                _upsert_booth(layout, node_id, booth_label)
                st.rerun()
        with b2:
            if st.button("Clear booth", key="builder_selected_clear_booth"):
                layout["booths"] = [b for b in layout["booths"] if b["node_id"] != node_id]
                st.rerun()

    with c2:
        st.markdown("**Entrance**")
        entrance_weight = st.number_input(
            "Entrance weight",
            min_value=0.01,
            value=float((existing_entrance or {}).get("weight", 1.0)),
            key="builder_selected_entrance_weight",
        )
        e1, e2 = st.columns(2)
        with e1:
            if st.button("Set entrance", key="builder_selected_set_entrance"):
                _upsert_entrance(layout, node_id, entrance_weight)
                st.rerun()
        with e2:
            if st.button("Clear entrance", key="builder_selected_clear_entrance"):
                layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != node_id]
                st.rerun()

    with c3:
        st.markdown("**Attractor**")
        attr_label = st.text_input("Attractor label", value=(existing_attractor or {}).get("label", f"Attractor {node_id}"), key="builder_selected_attr_label")
        attr_type = st.text_input("Attractor type", value=(existing_attractor or {}).get("type", "generic"), key="builder_selected_attr_type")
        attr_strength = st.number_input("Strength", min_value=0.1, value=float((existing_attractor or {}).get("strength", 1.0)), key="builder_selected_attr_strength")
        attr_draw_rate = st.number_input("Draw rate", min_value=0.0, max_value=1.0, value=float((existing_attractor or {}).get("draw_rate", 0.3)), key="builder_selected_attr_draw_rate")
        attr_dwell = st.number_input("Dwell steps", min_value=1, value=int((existing_attractor or {}).get("dwell_steps", 3)), key="builder_selected_attr_dwell")
        attr_capacity = st.number_input("Queue slots", min_value=1, value=int((existing_attractor or {}).get("capacity", 2)), key="builder_selected_attr_capacity")
        attr_max_wait = st.number_input("Max queue wait steps", min_value=0, value=int((existing_attractor or {}).get("max_wait_steps", 20)), key="builder_selected_attr_max_wait")
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Set attractor", key="builder_selected_set_attractor"):
                _upsert_attractor(layout, node_id, attr_label, attr_type, attr_strength, attr_draw_rate, int(attr_dwell), int(attr_capacity), int(attr_max_wait))
                st.rerun()
        with a2:
            if st.button("Clear attractor", key="builder_selected_clear_attractor"):
                layout["attractors"] = [a for a in layout["attractors"] if a["node_id"] != node_id]
                st.rerun()


def render() -> None:
    st.subheader("Layout Builder")
    layouts = list_layouts()
    choices = ["Create new"] + layouts
    selected = st.selectbox("Layout", choices, key="builder_layout_select")

    if selected == "Create new":
        if "builder_working_layout" not in st.session_state:
            st.session_state.builder_working_layout = new_layout_template()
            st.session_state.builder_layout_id = None
    else:
        if st.session_state.get("builder_layout_id") != selected:
            st.session_state.builder_working_layout = load_layout(selected)
            st.session_state.builder_layout_id = selected

    layout = st.session_state.builder_working_layout

    st.text_input("Layout Name", value=layout["meta"].get("name", "Untitled Layout"), key="builder_layout_name")
    layout["meta"]["name"] = st.session_state.builder_layout_name

    up = st.file_uploader("Upload floorplan", type=["png", "jpg", "jpeg"], key="builder_image_upload")
    if up is not None and st.button("Save uploaded image", key="builder_save_image_btn"):
        img_name = _safe_image_name(layout["meta"]["name"], up.name)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (IMAGE_DIR / img_name).write_bytes(up.getvalue())
        old = layout.get("image", {}).get("filename")
        if old and (IMAGE_DIR / old).exists():
            (IMAGE_DIR / old).unlink()
        layout["image"] = {"filename": img_name}
        st.success("Image saved")

    if st.button("Delete floorplan image", key="builder_delete_image_btn"):
        old = layout.get("image", {}).get("filename")
        if old and (IMAGE_DIR / old).exists():
            (IMAGE_DIR / old).unlink()
        layout["image"] = {"filename": None}

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Delete layout", key="builder_delete_layout_btn") and st.session_state.get("builder_layout_id"):
            delete_layout(st.session_state.builder_layout_id)
            st.session_state.builder_working_layout = new_layout_template()
            st.session_state.builder_layout_id = None
            st.rerun()
    with col_b:
        if st.button("Save layout", key="builder_save_layout_btn"):
            lid = save_layout(layout, st.session_state.get("builder_layout_id"))
            st.session_state.builder_layout_id = lid
            st.success(f"Saved as {lid}")
    with col_c:
        if st.button("Clear all nodes & paths", key="builder_clear_all_graph_btn"):
            layout["nodes"] = []
            layout["edges"] = []
            layout["booths"] = []
            layout["entrances"] = []
            layout["attractors"] = []
            st.session_state.builder_selected_node = None
            st.session_state.builder_connect_first_node = None
            st.info("Cleared all nodes, paths, and node-linked entities.")
            st.rerun()

    preview = _draw_preview(layout)
    preview = _draw_scale_key(preview)
    st.image(preview, caption="Preview")

    st.markdown("### Graph editor")
    sk1, sk2, sk3, sk4 = st.columns(4)
    with sk1:
        st.number_input("Scale key pixels", min_value=20, max_value=2000, value=int(st.session_state.get("builder_scale_px", 120)), step=5, key="builder_scale_px")
    with sk2:
        st.number_input("Scale key distance", min_value=0.1, max_value=10000.0, value=float(st.session_state.get("builder_scale_distance", 10.0)), step=0.5, key="builder_scale_distance")
    with sk3:
        st.text_input("Scale unit", value=st.session_state.get("builder_scale_unit", "m"), key="builder_scale_unit")
    with sk4:
        st.number_input("Walk speed for estimate (unit/min)", min_value=1.0, max_value=10000.0, value=float(st.session_state.get("builder_scale_walk_speed", 80.0)), step=1.0, key="builder_scale_walk_speed")

    click_mode = st.radio(
        "Click mode",
        ["Manual add node", "Auto add node", "Connect nodes", "Paint main paths", "Intersections", "Select node"],
        key="builder_click_mode",
        horizontal=True,
    )
    prev_mode = st.session_state.get("builder_prev_click_mode")
    if prev_mode != click_mode:
        _reset_mode_selection_state()
        st.session_state.builder_prev_click_mode = click_mode

    connect_main = st.checkbox("Connect mode: mark created edges as main", key="builder_connect_main")
    intersections_tolerance = int(
        st.number_input(
            "Intersections tolerance (px)",
            min_value=2,
            max_value=80,
            value=18,
            key="builder_intersections_tolerance",
        )
    )
    click = streamlit_image_coordinates(preview, key="builder_image_click")
    if click:
        st.caption(f"Last click: x={int(click['x'])}, y={int(click['y'])}")

    if click_mode == "Auto add node":
        before_nodes = len(layout.get("nodes", []))
        _handle_click_auto_add(layout, click)
        if len(layout.get("nodes", [])) != before_nodes:
            st.rerun()
    elif click_mode == "Connect nodes":
        first = st.session_state.get("builder_connect_first_node")
        if first is not None:
            st.info(f"Path mode: first node selected = {first}. Click second node.")
        before_edges = len(layout.get("edges", []))
        msg = _handle_click_connect(layout, click, connect_main)
        if msg:
            st.info(msg)
        if len(layout.get("edges", [])) != before_edges or (msg and "Updated main=True" in msg):
            st.rerun()
    elif click_mode == "Paint main paths":
        msg = _handle_click_paint_main(layout, click)
        if msg:
            st.info(msg)
            if msg.startswith("Marked edge"):
                st.rerun()
    elif click_mode == "Intersections":
        msg, added = _handle_click_intersections(layout, click, intersections_tolerance)
        if msg:
            st.info(msg)
        if added > 0:
            st.rerun()
    elif click_mode == "Select node":
        msg = _handle_click_select(layout, click)
        if msg:
            st.info(msg)
        _render_selected_node_editor(layout)

    if st.button("Add node at last click", key="builder_add_node_btn"):
        if click:
            nid = 1 + max([n["id"] for n in layout.get("nodes", [])], default=0)
            layout["nodes"].append({"id": nid, "x": int(click["x"]), "y": int(click["y"])})
            st.rerun()
        else:
            st.warning("Click the preview image first to place a node.")

    node_ids = [n["id"] for n in layout.get("nodes", [])]
    if node_ids:
        c1, c2, c3 = st.columns(3)
        with c1:
            s = st.selectbox("Edge source", node_ids, key="builder_edge_source")
        with c2:
            t = st.selectbox("Edge target", node_ids, key="builder_edge_target")
        with c3:
            is_main = st.checkbox("Paint main edge", key="builder_edge_main")
        if st.button("Add/mark edge", key="builder_add_edge_btn") and s != t:
            pair = tuple(sorted((s, t)))
            existing = next((e for e in layout["edges"] if tuple(sorted((e["source"], e["target"]))) == pair), None)
            if existing:
                existing["is_main"] = existing.get("is_main", False) or is_main
            else:
                layout["edges"].append({"source": s, "target": t, "is_main": bool(is_main)})
            st.rerun()

        st.markdown("#### Place booth / entrance / attractor")
        bcol, ecol, acol = st.columns(3)
        with bcol:
            bn = st.selectbox("Booth node", node_ids, key="builder_booth_node")
            bl = st.text_input("Booth label", key="builder_booth_label")
            if st.button("Add booth", key="builder_add_booth_btn"):
                if not any(b["node_id"] == bn for b in layout["booths"]):
                    layout["booths"].append({"node_id": bn, "label": bl or f"Booth {bn}"})
                    st.rerun()
        with ecol:
            en = st.selectbox("Entrance node", node_ids, key="builder_entrance_node")
            ew = st.number_input("Entrance weight", min_value=0.01, value=1.0, key="builder_entrance_weight")
            if st.button("Add entrance", key="builder_add_entrance_btn"):
                layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != en]
                layout["entrances"].append({"node_id": en, "weight": float(ew)})
                st.rerun()
        with acol:
            an = st.selectbox("Attractor node", node_ids, key="builder_attr_node")
            al = st.text_input("Attractor label", key="builder_attr_label")
            at = st.text_input("Attractor type", value="generic", key="builder_attr_type")
            a_strength = st.number_input("Strength", min_value=0.1, value=1.0, key="builder_attr_strength")
            a_draw = st.number_input("Draw rate", min_value=0.0, max_value=1.0, value=0.3, key="builder_attr_draw")
            a_dwell = st.number_input("Dwell steps", min_value=1, value=3, key="builder_attr_dwell")
            a_cap = st.number_input("Queue slots", min_value=1, value=2, key="builder_attr_capacity")
            a_wait = st.number_input("Max queue wait steps", min_value=0, value=20, key="builder_attr_max_wait")
            if st.button("Add attractor", key="builder_add_attr_btn"):
                layout["attractors"] = [a for a in layout["attractors"] if a["node_id"] != an]
                layout["attractors"].append(
                    {
                        "node_id": an,
                        "label": al or f"Attractor {an}",
                        "type": at,
                        "strength": float(a_strength),
                        "draw_rate": float(a_draw),
                        "dwell_steps": int(a_dwell),
                        "capacity": int(a_cap),
                        "max_wait_steps": int(a_wait),
                    }
                )
                st.rerun()

        edge_labels = [f"{i}: {e['source']}-{e['target']} ({'main' if e.get('is_main') else 'normal'})" for i, e in enumerate(layout.get("edges", []))]
        if edge_labels:
            del_edge_label = st.selectbox("Delete path", edge_labels, key="builder_delete_edge")
            if st.button("Delete selected path", key="builder_delete_edge_btn"):
                del_idx = int(del_edge_label.split(":", 1)[0])
                if 0 <= del_idx < len(layout["edges"]):
                    layout["edges"].pop(del_idx)
                    st.rerun()

        del_node = st.selectbox("Delete node", node_ids, key="builder_delete_node")
        if st.button("Delete selected node", key="builder_delete_node_btn"):
            layout["nodes"] = [n for n in layout["nodes"] if n["id"] != del_node]
            layout["edges"] = [e for e in layout["edges"] if e["source"] != del_node and e["target"] != del_node]
            layout["booths"] = [b for b in layout["booths"] if b["node_id"] != del_node]
            layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != del_node]
            layout["attractors"] = [a for a in layout["attractors"] if a["node_id"] != del_node]
            if st.session_state.get("builder_selected_node") == del_node:
                st.session_state.builder_selected_node = None
            st.rerun()

    st.markdown("### Current layout data")
    st.write("Nodes", layout.get("nodes", []))
    st.write("Edges", layout.get("edges", []))
    st.write("Booths", layout.get("booths", []))
    st.write("Entrances", layout.get("entrances", []))
    st.write("Attractors", layout.get("attractors", []))
