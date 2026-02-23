from __future__ import annotations

import streamlit as st

from defaults_store import default_preset_template, delete_preset, list_presets, load_preset, save_preset


FLOAT_FIELDS = [
    ("peak_hours", 0.0, 24.0, 0.1),
    ("peak_pct", 0.0, 1.0, 0.01),
    ("minutes_deviation", 0.0, 120.0, 1.0),
    ("turnback_rate", 0.0, 1.0, 0.01),
    ("congestion_alpha", 0.0, 10.0, 0.01),
    ("goal_bias", 0.1, 10.0, 0.1),
    ("attractor_pull_chance", 0.0, 1.0, 0.01),
    ("couples_rate", 0.0, 1.0, 0.01),
    ("main_loyal_multiplier", 0.1, 10.0, 0.1),
    ("explorer_novelty_bias", 0.0, 1.0, 0.01),
]


INT_FIELDS = [
    ("sims", 1, 1000),
    ("steps_per_minute", 1, 20),
    ("seed", 0, 1_000_000),
    ("pull_check_every_n_steps", 1, 100),
    ("attractor_cooldown_steps", 0, 200),
]


MIX_FIELDS = [
    ("pct_wanderer", 0.0, 1.0, 0.01),
    ("pct_mission", 0.0, 1.0, 0.01),
    ("pct_explorer", 0.0, 1.0, 0.01),
    ("pct_main", 0.0, 1.0, 0.01),
]


def _float_dual(field: str, cfg: dict, min_v: float, max_v: float, step: float) -> float:
    c1, c2 = st.columns([3, 1])
    with c1:
        slider_v = st.slider(f"{field} slider", min_value=min_v, max_value=max_v, value=float(cfg[field]), step=step, key=f"defaults_slider_{field}")
    with c2:
        box_v = st.number_input(f"{field} value", min_value=min_v, max_value=max_v, value=float(slider_v), step=step, key=f"defaults_box_{field}")
    return float(box_v)


def render() -> None:
    st.subheader("Defaults Presets")

    if "defaults_working" not in st.session_state:
        st.session_state.defaults_working = default_preset_template()

    presets = list_presets()
    selected = st.selectbox("Preset", ["(new)"] + presets, key="defaults_select")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Load selected", key="defaults_load_btn") and selected != "(new)":
            st.session_state.defaults_working = load_preset(selected)
    with c2:
        if st.button("Reset to template", key="defaults_reset_btn"):
            st.session_state.defaults_working = default_preset_template()
    with c3:
        if st.button("Delete selected", key="defaults_delete_btn") and selected != "(new)":
            delete_preset(selected)
            st.session_state.defaults_working = default_preset_template()
            st.rerun()

    cfg = st.session_state.defaults_working

    for f, low, high in INT_FIELDS:
        cfg[f] = int(st.number_input(f, min_value=low, max_value=high, value=int(cfg[f]), key=f"defaults_int_{f}"))

    for f, low, high, step in FLOAT_FIELDS:
        cfg[f] = _float_dual(f, cfg, low, high, step)

    st.markdown("#### Personality Mix")
    for f, low, high, step in MIX_FIELDS:
        cfg[f] = _float_dual(f, cfg, low, high, step)

    st.markdown("#### Heatmap Defaults")
    h = cfg.setdefault("heatmap_defaults", {})
    h["show_edges"] = st.checkbox("show_edges", value=bool(h.get("show_edges", True)), key="defaults_heat_show_edges")
    h["show_nodes"] = st.checkbox("show_nodes", value=bool(h.get("show_nodes", True)), key="defaults_heat_show_nodes")
    h["intensity"] = _float_dual("intensity", {"intensity": h.get("intensity", 0.9)}, 0.1, 2.0, 0.05)
    h["max_w"] = int(st.number_input("max_w", min_value=1, max_value=30, value=int(h.get("max_w", 12)), key="defaults_heat_max_w"))

    name = st.text_input("Preset name", value=(selected if selected != "(new)" else "default"), key="defaults_name")
    if st.button("Save preset", key="defaults_save_btn"):
        pid = save_preset(name, cfg)
        st.success(f"Saved preset {pid}")
