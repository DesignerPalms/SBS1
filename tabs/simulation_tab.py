from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from builder.heatmap import draw_heatmap_overlay
from defaults_store import default_preset_template, list_presets, load_preset
from graph_io import IMAGE_DIR, list_layouts, load_layout
from sim import SegmentConfig, run_simulation


def _sim_state_from_preset(preset: dict) -> None:
    for k, v in preset.items():
        st.session_state[f"sim_{k}"] = v


def _sim_cfg() -> dict:
    template = default_preset_template()
    cfg = {}
    for k, v in template.items():
        cfg[k] = st.session_state.get(f"sim_{k}", v)
    return cfg


def _segment_impressions(sim_result: dict, attendance: int) -> dict[str, float]:
    c = max(1, int(sim_result.get("concurrent_people", 1)))
    out = {}
    for booth_id, s in sim_result.get("booth_summary", {}).items():
        out[booth_id] = s["mean_score"] * (attendance / c)
    return out


def render() -> None:
    st.subheader("Simulation")

    layout_ids = list_layouts()
    if not layout_ids:
        st.info("Create a layout first.")
        return

    layout_id = st.selectbox("Layout", layout_ids, key="sim_layout_select")
    layout = load_layout(layout_id)

    preset_ids = list_presets()
    preset_choice = st.selectbox("Defaults preset", ["(template)"] + preset_ids, key="sim_preset_select")
    if st.button("Load preset", key="sim_load_preset_btn"):
        preset = default_preset_template() if preset_choice == "(template)" else load_preset(preset_choice)
        _sim_state_from_preset(preset)

    cfg = _sim_cfg()

    total_attendance = int(st.number_input("total_attendance", min_value=1, value=10000, key="sim_total_attendance"))
    total_show_hours = float(st.number_input("total_show_hours", min_value=0.1, value=8.0, step=0.1, key="sim_total_hours"))
    avg_minutes = float(st.number_input("avg_minutes_on_floor", min_value=1.0, value=90.0, step=1.0, key="sim_avg_minutes"))

    cfg["peak_hours"] = float(st.number_input("peak_hours", min_value=0.0, max_value=total_show_hours, value=float(cfg["peak_hours"]), step=0.1, key="sim_peak_hours"))
    cfg["peak_pct"] = float(st.slider("peak_pct", 0.0, 1.0, float(cfg["peak_pct"]), 0.01, key="sim_peak_pct"))
    cfg["minutes_deviation"] = float(st.number_input("minutes_deviation (+/- minutes, bell curve)", min_value=0.0, max_value=180.0, value=float(cfg.get("minutes_deviation", 30.0)), step=1.0, key="sim_minutes_deviation"))

    with st.expander("Realism controls", expanded=False):
        cfg["arrival_wave_strength"] = float(st.slider("arrival_wave_strength", 0.0, 1.0, float(cfg.get("arrival_wave_strength", 0.15)), 0.01, key="sim_arrival_wave_strength"))
        cfg["arrival_wave_frequency"] = float(st.number_input("arrival_wave_frequency", min_value=0.1, max_value=8.0, value=float(cfg.get("arrival_wave_frequency", 2.0)), step=0.1, key="sim_arrival_wave_frequency"))
        cfg["event_start_min"] = float(st.number_input("event_start_min", min_value=0.0, value=float(cfg.get("event_start_min", 120.0)), step=1.0, key="sim_event_start_min"))
        cfg["event_duration_min"] = float(st.number_input("event_duration_min", min_value=0.0, value=float(cfg.get("event_duration_min", 30.0)), step=1.0, key="sim_event_duration_min"))
        cfg["event_multiplier"] = float(st.number_input("event_multiplier", min_value=1.0, value=float(cfg.get("event_multiplier", 1.2)), step=0.1, key="sim_event_multiplier"))
        cfg["forward_bias"] = float(st.slider("forward_bias", 0.0, 5.0, float(cfg.get("forward_bias", 1.0)), 0.05, key="sim_forward_bias"))
        cfg["pixels_per_10m"] = float(st.number_input("pixels_per_10m", min_value=10.0, max_value=3000.0, value=float(cfg.get("pixels_per_10m", 150.0)), step=1.0, key="sim_pixels_per_10m"))

    if st.button("Run dual simulation", key="sim_run_btn"):
        peak_att = int(round(total_attendance * cfg["peak_pct"]))
        off_att = max(0, total_attendance - peak_att)
        off_hours = max(0.1, total_show_hours - cfg["peak_hours"])

        progress = st.progress(0)
        status = st.empty()

        def cb(pct: float, txt: str) -> None:
            progress.progress(int(pct * 100))
            status.text(txt)

        peak = run_simulation(layout, cfg, SegmentConfig(peak_att, cfg["peak_hours"] or 0.1, avg_minutes), progress_cb=cb, progress_offset=0.0, progress_span=0.5)
        off = run_simulation(layout, cfg, SegmentConfig(off_att, off_hours, avg_minutes), progress_cb=cb, progress_offset=0.5, progress_span=0.5)
        progress.progress(100)
        status.text("Done")

        peak_imp = _segment_impressions(peak, peak_att)
        off_imp = _segment_impressions(off, off_att)

        rows = []
        booth_ids = sorted(set(peak_imp.keys()) | set(off_imp.keys()))
        for b in booth_ids:
            total_imp = peak_imp.get(b, 0.0) + off_imp.get(b, 0.0)
            denom = total_attendance * (avg_minutes / 60.0)
            per_1000 = (total_imp / denom * 1000.0) if denom > 0 else 0.0
            rows.append(
                {
                    "booth_id": b,
                    "peak_est_total_impressions": peak_imp.get(b, 0.0),
                    "off_est_total_impressions": off_imp.get(b, 0.0),
                    "total_show_est_impressions": total_imp,
                    "show_impressions_per_1000_attendee_hours": per_1000,
                    "peak_mean_score": peak["booth_summary"].get(b, {}).get("mean_score", 0.0),
                    "peak_std_score": peak["booth_summary"].get(b, {}).get("std_score", 0.0),
                    "off_mean_score": off["booth_summary"].get(b, {}).get("mean_score", 0.0),
                    "off_std_score": off["booth_summary"].get(b, {}).get("std_score", 0.0),
                }
            )
        st.dataframe(pd.DataFrame(rows))

        queue_rows = [{"node_id": k, "mean_wait_steps": v} for k, v in peak.get("queue_wait_mean", {}).items()]
        if queue_rows:
            st.caption("Peak queue wait (mean steps)")
            st.dataframe(pd.DataFrame(queue_rows))

        heat_mode = st.selectbox("Heatmap mode", ["rank_bins", "percentile", "value"], key="sim_heat_mode")
        bins = st.slider("rank bins", 3, 9, 5, key="sim_heat_bins") if heat_mode == "rank_bins" else 5

        base_name = layout.get("image", {}).get("filename")
        base_img = Image.open(IMAGE_DIR / base_name).convert("RGB") if base_name and (IMAGE_DIR / base_name).exists() else Image.new("RGB", (900, 600), "white")

        hcfg = cfg.get("heatmap_defaults", {})
        peak_img = draw_heatmap_overlay(
            layout,
            base_img,
            peak.get("node_visit_mean", {}),
            peak.get("edge_visit_mean", {}),
            mode=heat_mode,
            bins=bins,
            show_edges=bool(hcfg.get("show_edges", True)),
            show_nodes=bool(hcfg.get("show_nodes", True)),
            intensity=float(hcfg.get("intensity", 0.9)),
            max_w=int(hcfg.get("max_w", 12)),
        )
        off_img = draw_heatmap_overlay(
            layout,
            base_img,
            off.get("node_visit_mean", {}),
            off.get("edge_visit_mean", {}),
            mode=heat_mode,
            bins=bins,
            show_edges=bool(hcfg.get("show_edges", True)),
            show_nodes=bool(hcfg.get("show_nodes", True)),
            intensity=float(hcfg.get("intensity", 0.9)),
            max_w=int(hcfg.get("max_w", 12)),
        )

        st.image(peak_img, caption="Peak heatmap")
        st.image(off_img, caption="Off-peak heatmap")
