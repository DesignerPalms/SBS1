from __future__ import annotations

import streamlit as st

from tabs.builder_tab import render as render_builder
from tabs.defaults_tab import render as render_defaults
from tabs.simulation_tab import render as render_simulation


st.set_page_config(page_title="Show Booth Scorer", layout="wide")
st.title("Show Booth Scorer")

builder_tab, sim_tab, defaults_tab = st.tabs(["Layout Builder", "Simulation", "Defaults Presets"])

with builder_tab:
    render_builder()
with sim_tab:
    render_simulation()
with defaults_tab:
    render_defaults()
