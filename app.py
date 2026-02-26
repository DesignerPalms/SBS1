from __future__ import annotations

import streamlit as st

from tabs.builder_tab import render as render_builder
from tabs.defaults_tab import render as render_defaults
from tabs.saved_sims_tab import render as render_saved_sims
from tabs.simulation_tab import render as render_simulation


st.set_page_config(page_title="Show Booth Scorer", layout="wide")
st.title("Show Booth Scorer")

builder_tab, sim_tab, saved_tab, defaults_tab = st.tabs(["Layout Builder", "Simulation", "Saved Sims", "Defaults Presets"])

with builder_tab:
    render_builder()
with sim_tab:
    render_simulation()
with saved_tab:
    render_saved_sims()
with defaults_tab:
    render_defaults()
