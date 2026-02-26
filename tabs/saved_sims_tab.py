from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from sim_store import SIM_IMAGES_DIR, delete_sim_run, list_sim_runs, load_sim_run


def render() -> None:
    st.subheader("Saved Sims")
    runs = list_sim_runs()
    if not runs:
        st.info("No saved simulations yet. Run a simulation and click Save sim.")
        return

    run_id = st.selectbox("Saved simulation", runs, key="saved_sims_select")
    run = load_sim_run(run_id)

    c1, c2 = st.columns(2)
    with c1:
        st.write("Meta", run.get("meta", {}))
    with c2:
        if st.button("Delete saved sim", key="saved_sims_delete_btn"):
            delete_sim_run(run_id)
            st.success("Deleted")
            st.rerun()

    rows = run.get("summary_rows", [])
    if rows:
        st.markdown("### Booth summary")
        st.dataframe(pd.DataFrame(rows))

    st.markdown("### Heatmaps")
    peak_img_name = run.get("artifacts", {}).get("peak_heatmap_image")
    off_img_name = run.get("artifacts", {}).get("off_heatmap_image")
    if peak_img_name and (SIM_IMAGES_DIR / peak_img_name).exists():
        st.image(Image.open(SIM_IMAGES_DIR / peak_img_name), caption="Saved peak heatmap")
    if off_img_name and (SIM_IMAGES_DIR / off_img_name).exists():
        st.image(Image.open(SIM_IMAGES_DIR / off_img_name), caption="Saved off-peak heatmap")

    st.markdown("### Peak attractor debug")
    debug_peak = run.get("peak", {}).get("attractor_debug", {})
    if debug_peak:
        st.dataframe(pd.DataFrame([{"node_id": k, **v} for k, v in debug_peak.items()]))

    st.markdown("### Off-peak attractor debug")
    debug_off = run.get("off", {}).get("attractor_debug", {})
    if debug_off:
        st.dataframe(pd.DataFrame([{"node_id": k, **v} for k, v in debug_off.items()]))
