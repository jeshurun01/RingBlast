"""
app.py -- Streamlit web UI for xml_to_image.py

Run with:
    streamlit run app.py
"""

import csv
import hashlib
import io
import math
import os
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from xml_to_image import (
    build_charge_table,
    build_figure,
    build_pdf_bytes,
    build_report_figure,
    compute_stemming,
    parse_xml,
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _fig_to_png_bytes(fig, dpi):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf.getvalue()


def _preview_hash(df, settings, charge_params):
    """Hash of all inputs that affect the preview image."""
    df_bytes = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    rest = str(sorted(settings.items())) + str(
        sorted({k: v for k, v in charge_params.items() if k != "diameter_override_mm"}.items())
    )
    return hashlib.md5(df_bytes + rest.encode()).hexdigest()


def _report_csv_bytes(report_csv_rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Number", "Diameter (mm)", "Length (m)", "Actual meters",
                     "Stemming (m)", "Charge length (m)", "Charge (kg)",
                     "Actual charge", "Delay (ms)"])
    writer.writerows(report_csv_rows)
    return buf.getvalue().encode()


def _build_default_hole_df(holes, charge_params):
    rows = []
    dia_override = charge_params.get("diameter_override_mm", 0)
    for h in holes:
        depth = math.hypot(h["x2"] - h["x1"], h["y2"] - h["y1"])
        diameter = dia_override if dia_override > 0 else int(h["diameter_mm"])
        stemming = compute_stemming(
            depth, diameter,
            charge_params["stemming_multiplier"],
            charge_params["short_threshold"],
            charge_params["short_fixed"],
        )
        rows.append({
            "Hole":          h["name"] or h["id"],
            "Diameter (mm)": diameter,
            "Depth (m)":     round(depth, 3),
            "Stemming (m)":  round(stemming, 3),
            "Delay (ms)":    None,
        })
    return pd.DataFrame(rows)


# ── Page config ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="RingBlast",
    page_icon="🔩",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔩 RingBlast")
    st.caption("iRedes DRPPlan blast report generator")
    st.divider()

    company_name = st.text_input(
        "Company / project name",
        placeholder="e.g. Acme Mining — Block 22",
        help="Shown in the PDF report header",
    )
    st.divider()

    with st.expander("🎨  Visual style", expanded=False):
        color_hole       = st.color_picker("Drill holes",       "#000000")
        color_outline    = st.color_picker("Outline",           "#000000")
        color_dot        = st.color_picker("Collar / toe dots", "#000000")
        color_background = st.color_picker("Background",        "#ffffff")
        color_charge     = st.color_picker("Charge line",       "#cc0000")
        st.divider()
        linewidth_hole    = st.slider("Hole line width",    0.1, 3.0, 0.8, 0.1)
        linewidth_outline = st.slider("Outline line width", 0.1, 3.0, 0.8, 0.1)
        st.divider()
        dot_size       = st.slider("Dot size",          5,   100,  30)
        label_fontsize = st.slider("Label font size",   4.0, 14.0, 6.5, 0.5)
        title_fontsize = st.slider("Title font size",  10.0, 28.0, 18.0, 1.0)
        st.divider()
        delay_label_offset = st.slider("Delay label offset (m)", 0.0, 2.0, 0.35, 0.05,
                                       help="Perpendicular offset of the delay (ms) label from the toe")

    with st.expander("📐  Figure layout", expanded=False):
        show_grid        = st.checkbox("Show grid", value=True)
        scale_bar_length = st.number_input("Scale bar length (m)", min_value=0.5,
                                           max_value=50.0, value=5.0, step=0.5)
        col_w, col_h = st.columns(2)
        with col_w:
            fig_width  = st.number_input("Width (in)",  min_value=5.0, max_value=24.0,
                                         value=11.0, step=0.5)
        with col_h:
            fig_height = st.number_input("Height (in)", min_value=4.0, max_value=20.0,
                                         value=9.0, step=0.5)
        output_dpi = st.selectbox("Output DPI", [72, 100, 150, 200, 300], index=2)

    with st.expander("💣  Charging parameters", expanded=True):
        stemming_multiplier = st.number_input(
            "Stemming multiplier", min_value=5, max_value=50, value=20,
            help="Stemming = multiplier × (diameter mm / 1000) metres")
        short_threshold = st.number_input(
            "Short-hole threshold (m)", min_value=1.0, max_value=10.0,
            value=4.0, step=0.5,
            help="Holes shorter than this use the fixed stemming below")
        short_fixed = st.number_input(
            "Short-hole stemming (m)", min_value=0.1, max_value=5.0,
            value=1.5, step=0.1)
        explosive_density = st.number_input(
            "Explosive density (g/cc)", min_value=0.5, max_value=3.0,
            value=1.15, step=0.05)
        st.divider()
        diameter_override = st.number_input(
            "Hole diameter override (mm)", min_value=0, max_value=500, value=0, step=1,
            help="Set to 0 to use the diameter from the XML file. Any other value overrides all holes.")

settings = {
    "color_hole":        color_hole,
    "color_outline":     color_outline,
    "color_dot":         color_dot,
    "color_background":  color_background,
    "color_charge":      color_charge,
    "linewidth_hole":    linewidth_hole,
    "linewidth_outline": linewidth_outline,
    "dot_size":          dot_size,
    "label_fontsize":      label_fontsize,
    "title_fontsize":      title_fontsize,
    "delay_label_offset":  delay_label_offset,
    "show_grid":           show_grid,
    "scale_bar_length":  scale_bar_length,
    "fig_width":         fig_width,
    "fig_height":        fig_height,
}

charge_params = {
    "stemming_multiplier":   stemming_multiplier,
    "short_threshold":       short_threshold,
    "short_fixed":           short_fixed,
    "explosive_density_gcc": explosive_density,
    "diameter_override_mm":  diameter_override,
}

# ── Step 1 — Upload ──────────────────────────────────────────────────────────────

st.header("Step 1 — Upload XML files")
uploaded_files = st.file_uploader(
    "Select one or more iRedes DRPPlan .XML files",
    type=["xml"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

# Parse files when upload list changes
current_names = [uf.name for uf in uploaded_files] if uploaded_files else []
if current_names != st.session_state.get("uploaded_names", []):
    st.session_state["uploaded_names"] = current_names
    st.session_state["parsed_data"]    = {}
    st.session_state.pop("results", None)
    for key in [k for k in st.session_state
                if k.startswith("df_") or k.startswith("edited_") or k.startswith("de_")]:
        del st.session_state[key]

    if uploaded_files:
        errors = []
        for uf in uploaded_files:
            base = os.path.splitext(uf.name)[0]
            try:
                uf.seek(0)
                plan_name, plan_id, holes, segments = parse_xml(uf, filename=uf.name)
                st.session_state["parsed_data"][base] = {
                    "plan_name": plan_name, "plan_id": plan_id,
                    "holes": holes, "segments": segments,
                }
            except Exception as exc:
                errors.append(f"**{uf.name}**: {exc}")
        for e in errors:
            st.error(e)

# Show upload summary
if st.session_state.get("parsed_data"):
    n_files = len(st.session_state["parsed_data"])
    n_holes = sum(len(v["holes"]) for v in st.session_state["parsed_data"].values())
    st.success(f"{n_files} file{'s' if n_files > 1 else ''} loaded — {n_holes} holes total")

# ── Step 2 & 3 side by side ──────────────────────────────────────────────────────

if st.session_state.get("parsed_data"):
    st.divider()
    st.subheader("Step 2 — Edit hole data")
    st.caption("Stemming is auto-calculated from the sidebar parameters. "
               "Override per hole as needed and set delays. "
               "The plan preview updates live as you edit.")

    file_tabs = st.tabs(list(st.session_state["parsed_data"].keys()))

    for tab, (base, pdata) in zip(file_tabs, st.session_state["parsed_data"].items()):
        with tab:
            df_key = f"df_{base}"
            if df_key not in st.session_state:
                st.session_state[df_key] = _build_default_hole_df(pdata["holes"], charge_params)

            df_current = st.session_state.get(f"edited_{base}", st.session_state[df_key])

            # ── Two columns: editor left, live preview right ──────────────────
            col_editor, col_preview = st.columns([2, 3], gap="large")

            with col_editor:
                # Summary metrics
                avg_depth  = df_current["Depth (m)"].mean()
                avg_stem   = df_current["Stemming (m)"].mean()
                est_charge = (
                    df_current["Depth (m)"].sub(df_current["Stemming (m)"]).clip(lower=0)
                    * math.pi * (df_current["Diameter (mm)"] / 2000) ** 2
                    * explosive_density * 1000
                ).sum()
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Holes",        len(pdata["holes"]))
                mc2.metric("Avg depth",    f"{avg_depth:.2f} m")
                mc3.metric("Avg stemming", f"{avg_stem:.2f} m")
                mc4.metric("Est. charge",  f"{est_charge:.1f} kg")

                st.divider()

                col_btn, col_hint = st.columns([1, 3])
                with col_btn:
                    if st.button("↺ Reset stemming", key=f"recalc_{base}",
                                 help="Recalculate stemming from the sidebar parameters"):
                        st.session_state[df_key] = _build_default_hole_df(
                            pdata["holes"], charge_params)
                        for _k in [f"de_{base}", f"edited_{base}"]:
                            if _k in st.session_state:
                                del st.session_state[_k]
                        st.rerun()
                with col_hint:
                    st.caption("Edit **Stemming (m)** or **Delay (ms)**.")

                edited = st.data_editor(
                    st.session_state[df_key],
                    use_container_width=True,
                    column_config={
                        "Hole":
                            st.column_config.TextColumn("Hole", disabled=True),
                        "Diameter (mm)":
                            st.column_config.NumberColumn("Ø (mm)", disabled=False,
                                                          min_value=1, max_value=500, step=1),
                        "Depth (m)":
                            st.column_config.NumberColumn("Depth (m)", disabled=True,
                                                          format="%.3f"),
                        "Stemming (m)":
                            st.column_config.NumberColumn("Stemming (m)",
                                                          min_value=0.0, max_value=100.0,
                                                          format="%.2f"),
                        "Delay (ms)":
                            st.column_config.NumberColumn("Delay (ms)",
                                                          min_value=0, step=25),
                    },
                    hide_index=True,
                    key=f"de_{base}",
                )
                st.session_state[f"edited_{base}"] = edited

            with col_preview:
                # Live plan preview — only re-render when inputs actually change
                phash = _preview_hash(edited, settings, charge_params)
                png_cache_key  = f"preview_png_{base}"
                hash_cache_key = f"preview_hash_{base}"

                if st.session_state.get(hash_cache_key) != phash:
                    try:
                        stemming_overrides = dict(zip(edited["Hole"], edited["Stemming (m)"]))
                        diameter_overrides = dict(zip(edited["Hole"], edited["Diameter (mm)"]))
                        delay_map = {
                            row["Hole"]: int(row["Delay (ms)"])
                            for _, row in edited.iterrows()
                            if pd.notna(row["Delay (ms)"]) and row["Delay (ms)"] != ""
                        }
                        charge_data_preview = build_charge_table(
                            pdata["holes"],
                            stemming_overrides=stemming_overrides,
                            diameter_overrides=diameter_overrides,
                            delay_map=delay_map,
                            **{k: v for k, v in charge_params.items() if k != "diameter_override_mm"},
                        )
                        preview_settings = dict(settings)
                        preview_settings["fig_width"]  = 7
                        preview_settings["fig_height"] = 6
                        fig_preview, _ = build_figure(
                            pdata["plan_name"], pdata["plan_id"],
                            pdata["holes"], pdata["segments"],
                            preview_settings, charge_data_preview,
                        )
                        st.session_state[png_cache_key]  = _fig_to_png_bytes(fig_preview, 120)
                        st.session_state[hash_cache_key] = phash
                        plt.close(fig_preview)
                    except Exception as exc:
                        st.warning(f"Preview error: {exc}")

                if png_cache_key in st.session_state:
                    st.image(st.session_state[png_cache_key], use_container_width=True)

    # ── Step 3 — Generate ────────────────────────────────────────────────────────

    st.divider()
    st.subheader("Step 3 — Generate")

    if st.button("🚀  Generate blast report", type="primary", use_container_width=True):
        results = {}
        progress_bar = st.progress(0, text="Processing...")
        items = list(st.session_state["parsed_data"].items())

        for i, (base, pdata) in enumerate(items):
            progress_bar.progress(i / len(items), text=f"Processing {base}…")
            try:
                df = st.session_state.get(
                    f"edited_{base}",
                    st.session_state.get(
                        f"df_{base}",
                        _build_default_hole_df(pdata["holes"], charge_params),
                    ),
                )

                stemming_overrides = dict(zip(df["Hole"], df["Stemming (m)"]))
                diameter_overrides = dict(zip(df["Hole"], df["Diameter (mm)"]))
                delay_map = {
                    row["Hole"]: int(row["Delay (ms)"])
                    for _, row in df.iterrows()
                    if pd.notna(row["Delay (ms)"]) and row["Delay (ms)"] != ""
                }

                charge_data = build_charge_table(
                    pdata["holes"],
                    stemming_overrides=stemming_overrides,
                    diameter_overrides=diameter_overrides,
                    delay_map=delay_map,
                    **{k: v for k, v in charge_params.items() if k != "diameter_override_mm"},
                )

                fig_plan, _ = build_figure(
                    pdata["plan_name"], pdata["plan_id"],
                    pdata["holes"], pdata["segments"],
                    settings, charge_data,
                )
                plan_png = _fig_to_png_bytes(fig_plan, output_dpi)
                plt.close(fig_plan)

                fig_report, report_csv_rows = build_report_figure(
                    pdata["plan_name"], pdata["plan_id"],
                    pdata["holes"], pdata["segments"],
                    settings, charge_data,
                )
                report_png = _fig_to_png_bytes(fig_report, output_dpi)
                plt.close(fig_report)

                pdf_bytes = build_pdf_bytes(
                    pdata["plan_name"], pdata["plan_id"],
                    pdata["holes"], pdata["segments"],
                    settings, charge_data,
                    company=company_name,
                )

                total_charge = sum(r["charge_kg"] for r in charge_data)
                results[base] = {
                    "plan_png":     plan_png,
                    "report_png":   report_png,
                    "pdf":          pdf_bytes,
                    "csv":          _report_csv_bytes(report_csv_rows),
                    "total_charge": total_charge,
                    "n_holes":      len(charge_data),
                }
            except Exception as exc:
                st.error(f"Error processing **{base}**: {exc}")

            progress_bar.progress((i + 1) / len(items),
                                  text=f"Done {i + 1} / {len(items)}")

        progress_bar.empty()
        st.session_state["results"] = results
        st.rerun()


# ── Results ──────────────────────────────────────────────────────────────────────

if st.session_state.get("results"):
    results = st.session_state["results"]

    st.divider()
    st.header("Results")

    # Bulk ZIP download
    zip_name_input = st.text_input("ZIP file name", value="ringblast_output", key="zip_file_name")
    zip_file_name  = (zip_name_input.strip() or "ringblast_output")
    if not zip_file_name.endswith(".zip"):
        zip_file_name += ".zip"

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, data in results.items():
            zf.writestr(f"plans/{base}.png",              data["plan_png"])
            zf.writestr(f"reports_png/{base}_report.png", data["report_png"])
            zf.writestr(f"reports_pdf/{base}_report.pdf", data["pdf"])
            zf.writestr(f"csv/{base}_charge.csv",         data["csv"])
    zip_buf.seek(0)

    st.download_button(
        label=f"⬇  Download all ({len(results)} file{'s' if len(results) != 1 else ''}) as ZIP",
        data=zip_buf,
        file_name=zip_file_name,
        mime="application/zip",
        use_container_width=True,
        type="secondary",
    )

    st.divider()

    result_tabs = st.tabs(list(results.keys()))
    for tab, (base, data) in zip(result_tabs, results.items()):
        with tab:
            # Metrics row
            rm1, rm2 = st.columns(2)
            rm1.metric("Holes charged", data["n_holes"])
            rm2.metric("Total charge",  f"{data['total_charge']:.1f} kg")

            # Image tabs
            t_plan, t_report = st.tabs(["📐 Drill Plan", "📋 Blast Report"])
            with t_plan:
                st.image(data["plan_png"], use_container_width=True)
            with t_report:
                st.image(data["report_png"], use_container_width=True)

            # Download buttons
            st.divider()
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.download_button(
                label="⬇ Plan PNG",
                data=data["plan_png"],
                file_name=f"{base}.png",
                mime="image/png",
                key=f"dl_plan_{base}",
                use_container_width=True,
            )
            dc2.download_button(
                label="⬇ Report PNG",
                data=data["report_png"],
                file_name=f"{base}_report.png",
                mime="image/png",
                key=f"dl_report_{base}",
                use_container_width=True,
            )
            dc3.download_button(
                label="⬇ Report PDF",
                data=data["pdf"],
                file_name=f"{base}_report.pdf",
                mime="application/pdf",
                key=f"dl_pdf_{base}",
                use_container_width=True,
            )
            dc4.download_button(
                label="⬇ Charge CSV",
                data=data["csv"],
                file_name=f"{base}_charge.csv",
                mime="text/csv",
                key=f"dl_csv_{base}",
                use_container_width=True,
            )

