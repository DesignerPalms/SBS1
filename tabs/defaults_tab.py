from __future__ import annotations

import streamlit as st

from defaults_store import default_preset_template, delete_preset, list_presets, load_preset, save_preset


FLOAT_FIELDS = [
    ("peak_hours", 0.0, 24.0, 0.1),
    ("peak_pct", 0.0, 1.0, 0.01),
    ("minutes_deviation", 0.0, 120.0, 1.0),
    ("arrival_wave_strength", 0.0, 1.0, 0.01),
    ("arrival_wave_frequency", 0.1, 8.0, 0.1),
    ("event_start_min", 0.0, 1440.0, 1.0),
    ("event_duration_min", 0.0, 240.0, 1.0),
    ("event_multiplier", 1.0, 5.0, 0.1),
    ("main_event_pull_chance", 0.0, 1.0, 0.01),
    ("main_event_strength_multiplier", 1.0, 20.0, 0.1),
    ("turnback_rate", 0.0, 1.0, 0.01),
    ("forward_bias", 0.0, 5.0, 0.05),
    ("congestion_alpha", 0.0, 10.0, 0.01),
    ("goal_bias", 0.1, 10.0, 0.1),
    ("attractor_pull_chance", 0.0, 1.0, 0.01),
    ("group_prob_solo", 0.0, 1.0, 0.01),
    ("group_prob_couple", 0.0, 1.0, 0.01),
    ("group_prob_triple", 0.0, 1.0, 0.01),
    ("group_prob_quad", 0.0, 1.0, 0.01),
    ("group_cohesion", 0.1, 1.0, 0.01),
    ("repeat_edge_penalty", 0.01, 1.0, 0.01),
    ("novelty_bonus_initial", 0.0, 2.0, 0.01),
    ("novelty_decay_rate", 0.0, 2.0, 0.01),
    ("pixels_per_10m", 10.0, 3000.0, 1.0),
    ("main_loyal_multiplier", 0.1, 10.0, 0.1),
    ("explorer_novelty_bias", 0.0, 1.0, 0.01),
]


INT_FIELDS = [
    ("sims", 1, 1000),
    ("steps_per_minute", 1, 20),
    ("seed", 0, 1_000_000),
    ("pull_check_every_n_steps", 1, 100),
    ("attractor_cooldown_steps", 0, 200),
    ("memory_window_steps", 1, 100),
    ("booth_capacity", 1, 20),
    ("booth_service_steps", 1, 30),
    ("booth_max_queue_wait_steps", 0, 200),
]


MIX_FIELDS = [
    ("pct_wanderer", 0.0, 1.0, 0.01),
    ("pct_mission", 0.0, 1.0, 0.01),
    ("pct_explorer", 0.0, 1.0, 0.01),
    ("pct_main", 0.0, 1.0, 0.01),
]


HELP_TEXT: dict[str, str] = {
    "sims": "How many Monte Carlo runs to average. Low = faster, noisier. High = slower, more stable.",
    "steps_per_minute": "Simulation ticks per minute. Low = coarse movement. High = finer movement and heavier compute.",
    "seed": "Random seed for reproducibility. Same inputs + same seed => same results.",
    "peak_hours": "Hours considered peak. Higher shifts more simulated time into peak behavior.",
    "peak_pct": "Fraction of attendance during peak hours. Higher concentrates demand into peak segment.",
    "minutes_deviation": "Bell-curve spread around avg minutes on floor. Formula: sampled_minutes = avg_minutes + clamp(N(0, dev/3), -dev, +dev). Low = tighter around avg; high = wider spread.",
    "arrival_wave_strength": "Amplitude of cyclical arrival pulses. Formula: wave = 1 + strength * sin(2π * freq * t). 0 = flat arrivals; larger = stronger waves.",
    "arrival_wave_frequency": "How often arrival waves oscillate over a segment. Higher = more frequent surges.",
    "event_start_min": "Minute offset when an event spike starts.",
    "event_duration_min": "How long the event spike lasts.",
    "event_multiplier": "Arrival multiplier during event window. Formula: arrival_weight *= event_multiplier when event_start <= t <= event_end. 1 = no spike; larger = stronger surge.",
    "main_event_pull_chance": "Event-step assignment chance. Formula: if event active and rand() < pull_chance => step_goal = main_event_node. 0 = never, 1 = always.",
    "main_event_strength_multiplier": "Event directional boost. Formula (if neighbor gets closer to active main-event node): score *= main_event_strength_multiplier. 1 = no extra boost.",
    "turnback_rate": "Immediate backtrack penalty. Formula on reverse edge: score *= max(0.01, 1 - turnback_rate). 0 => no penalty, 1 => very strong penalty.",
    "forward_bias": "Heading momentum multiplier. Formula: score *= 1 + forward_bias * ((cos(theta)+1)/2). 0 = off; 1 = moderate; 2.6 = strong preference for going straight.",
    "congestion_alpha": "Congestion penalty strength. Formula: score *= 1 / (1 + congestion_alpha * edge_flow). Higher values avoid busy edges more aggressively.",
    "goal_bias": "Goal-seeking boost. Formula (if move reduces shortest-path distance to goal): score *= goal_bias. 1 = no extra bias; >1 pushes goal-directed movement.",
    "attractor_pull_chance": "Chance that attractor pull logic engages when checked.",
    "pull_check_every_n_steps": "How often pull opportunities are evaluated.",
    "attractor_cooldown_steps": "Cooldown after an attractor dwell before another immediate pull/dwell.",
    "pct_wanderer": "Share of attendees behaving as wanderers.",
    "pct_mission": "Share of attendees following mission/target-driven behavior.",
    "pct_explorer": "Share of attendees emphasizing exploration.",
    "pct_main": "Share of attendees preferring main paths.",
    "group_prob_solo": "Relative probability a spawned group has size 1.",
    "group_prob_couple": "Relative probability a spawned group has size 2.",
    "group_prob_triple": "Relative probability a spawned group has size 3.",
    "group_prob_quad": "Relative probability a spawned group has size 4.",
    "group_cohesion": "How tightly grouped/coordinated grouped agents behave. Higher = more cohesive.",
    "memory_window_steps": "Recent-edge memory length used to discourage repeating the same edges.",
    "repeat_edge_penalty": "Recent-edge repeat penalty. Formula: if edge in recent_window => score *= repeat_edge_penalty. 1 = no penalty; smaller means stronger avoidance.",
    "novelty_bonus_initial": "Novelty bonus scale. Formula: score *= 1 + novelty_bonus_initial * exp(-novelty_decay_rate * visits_to_node). Higher gives stronger exploration.",
    "novelty_decay_rate": "Novelty decay speed in exp term. Higher means the novelty bonus drops off faster as a node is revisited.",
    "pixels_per_10m": "Image scale calibration. Formula: px_per_m = pixels_per_10m / 10; sampled_px_per_min = sampled_m_per_min * px_per_m. Higher value increases traversable pixels per minute.",
    "booth_capacity": "Concurrent service slots at booth nodes. Higher = shorter queues.",
    "booth_service_steps": "How long booth service takes. Higher = longer waits at booths.",
    "booth_max_queue_wait_steps": "Max tolerated booth queue wait before abandoning queue behavior.",
    "main_loyal_multiplier": "Main-loyal edge boost. Formula: if edge.is_main => score *= main_loyal_multiplier for main-loyal personality. 1 = no special preference.",
    "explorer_novelty_bias": "Reserved explorer-specific novelty weight for future expansion.",
    "intensity": "Heatmap color intensity/opacity. Low = subtle; high = stronger overlay.",
    "max_w": "Max rendered edge stroke width in heatmaps.",
}


def _float_dual(field: str, cfg: dict, min_v: float, max_v: float, step: float) -> float:
    help_text = HELP_TEXT.get(field)
    c1, c2 = st.columns([3, 1])
    with c1:
        slider_v = st.slider(
            f"{field} slider",
            min_value=min_v,
            max_value=max_v,
            value=float(cfg[field]),
            step=step,
            key=f"defaults_slider_{field}",
            help=help_text,
        )
    with c2:
        box_v = st.number_input(
            f"{field} value",
            min_value=min_v,
            max_value=max_v,
            value=float(slider_v),
            step=step,
            key=f"defaults_box_{field}",
            help=help_text,
        )
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

    st.caption("Tip: hover the ⓘ icon on each control label to see what low vs high values do.")

    for f, low, high in INT_FIELDS:
        cfg[f] = int(
            st.number_input(
                f,
                min_value=low,
                max_value=high,
                value=int(cfg[f]),
                key=f"defaults_int_{f}",
                help=HELP_TEXT.get(f),
            )
        )

    for f, low, high, step in FLOAT_FIELDS:
        cfg[f] = _float_dual(f, cfg, low, high, step)

    st.markdown("#### Personality Mix")
    for f, low, high, step in MIX_FIELDS:
        cfg[f] = _float_dual(f, cfg, low, high, step)

    st.markdown("#### Heatmap Defaults")
    h = cfg.setdefault("heatmap_defaults", {})
    h["show_edges"] = st.checkbox("show_edges", value=bool(h.get("show_edges", True)), key="defaults_heat_show_edges", help="Toggle rendering of edge heat in the heatmap overlay.")
    h["show_nodes"] = st.checkbox("show_nodes", value=bool(h.get("show_nodes", True)), key="defaults_heat_show_nodes", help="Toggle rendering of node heat in the heatmap overlay.")
    h["intensity"] = _float_dual("intensity", {"intensity": h.get("intensity", 0.9)}, 0.1, 2.0, 0.05)
    h["max_w"] = int(st.number_input("max_w", min_value=1, max_value=30, value=int(h.get("max_w", 12)), key="defaults_heat_max_w", help=HELP_TEXT.get("max_w")))

    name = st.text_input("Preset name", value=(selected if selected != "(new)" else "default"), key="defaults_name")
    if st.button("Save preset", key="defaults_save_btn"):
        pid = save_preset(name, cfg)
        st.success(f"Saved preset {pid}")
