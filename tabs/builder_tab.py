from __future__ import annotations

from datetime import datetime
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

    return img


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

    col_a, col_b = st.columns(2)
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

    preview = _draw_preview(layout)
    st.image(preview, caption="Preview")

    st.markdown("### Graph editor")
    click = streamlit_image_coordinates(preview, key="builder_image_click")
    if click:
        st.caption(f"Last click: x={int(click['x'])}, y={int(click['y'])}")

    if st.button("Add node at last click", key="builder_add_node_btn"):
        if click:
            nid = 1 + max([n["id"] for n in layout.get("nodes", [])], default=0)
            layout["nodes"].append({"id": nid, "x": int(click["x"]), "y": int(click["y"])})
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

        st.markdown("#### Place booth / entrance / attractor")
        bcol, ecol, acol = st.columns(3)
        with bcol:
            bn = st.selectbox("Booth node", node_ids, key="builder_booth_node")
            bl = st.text_input("Booth label", key="builder_booth_label")
            if st.button("Add booth", key="builder_add_booth_btn"):
                if not any(b["node_id"] == bn for b in layout["booths"]):
                    layout["booths"].append({"node_id": bn, "label": bl or f"Booth {bn}"})
        with ecol:
            en = st.selectbox("Entrance node", node_ids, key="builder_entrance_node")
            ew = st.number_input("Entrance weight", min_value=0.01, value=1.0, key="builder_entrance_weight")
            if st.button("Add entrance", key="builder_add_entrance_btn"):
                layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != en]
                layout["entrances"].append({"node_id": en, "weight": float(ew)})
        with acol:
            an = st.selectbox("Attractor node", node_ids, key="builder_attr_node")
            al = st.text_input("Attractor label", key="builder_attr_label")
            at = st.text_input("Attractor type", value="generic", key="builder_attr_type")
            a_strength = st.number_input("Strength", min_value=0.1, value=1.0, key="builder_attr_strength")
            a_draw = st.number_input("Draw rate", min_value=0.0, max_value=1.0, value=0.3, key="builder_attr_draw")
            a_dwell = st.number_input("Dwell steps", min_value=1, value=3, key="builder_attr_dwell")
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
                    }
                )

        del_node = st.selectbox("Delete node", node_ids, key="builder_delete_node")
        if st.button("Delete selected node", key="builder_delete_node_btn"):
            layout["nodes"] = [n for n in layout["nodes"] if n["id"] != del_node]
            layout["edges"] = [e for e in layout["edges"] if e["source"] != del_node and e["target"] != del_node]
            layout["booths"] = [b for b in layout["booths"] if b["node_id"] != del_node]
            layout["entrances"] = [e for e in layout["entrances"] if e["node_id"] != del_node]
            layout["attractors"] = [a for a in layout["attractors"] if a["node_id"] != del_node]

    st.markdown("### Current layout data")
    st.write("Nodes", layout.get("nodes", []))
    st.write("Edges", layout.get("edges", []))
    st.write("Booths", layout.get("booths", []))
    st.write("Entrances", layout.get("entrances", []))
    st.write("Attractors", layout.get("attractors", []))
