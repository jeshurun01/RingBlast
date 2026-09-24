"""
generate_batch_reports.py -- RingBlast batch report generator (CLI companion to app.py).

Uses the SAME report-generation path as the Streamlit app:
    parse_xml -> build_charge_table -> build_pdf_bytes -> merge_pdf_bytes
with the app's DEFAULT charge parameters and visual settings, so the output
matches what the web UI would produce for the same XMLs.

Deliverables for a batch of iRedes DRPPlan XMLs (default names use the batch
stope label derived from the input XML names, e.g. B27_S8):
  1. <STOPE>_Combined_RingBlast_Report.pdf -- per-ring blast report, one PDF
     merged. Use --combined-name to choose a descriptive, safely sanitized
     name instead.
  2. <STOPE>_Top_View_All_Rings.pdf       -- ONE page: top view of every ring
  3. <STOPE>_RingBlast_Report_Package.zip -- individual PDFs + charge CSVs
     (reports_pdf/, csv/) + the combined report + the top view + summary

Usage:
    .venv/bin/python scripts/generate_batch_reports.py \
        /path/to/XMLs/*.XML -o /path/to/output_dir
"""

import argparse
import glob
import io
import json
import os
import sys
import zipfile

# Allow running from anywhere: put the RingBlast project root on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from xml_to_image import (
    build_charge_table,
    build_figure,
    build_pdf_bytes,
    hole_length,
    merge_pdf_bytes,
    parse_xml,
    project_plan,
)
from app_utils import (
    batch_stope_label,
    combined_report_filename,
    stope_label_from_name,
)

# ── App defaults (must match app.py sidebar defaults) ─────────────────────────
DEFAULT_SETTINGS = {
    "color_hole":        "#000000",
    "color_outline":     "#000000",
    "color_dot":         "#000000",
    "color_background":  "#ffffff",
    "color_charge":      "#cc0000",
    "linewidth_hole":    0.8,
    "linewidth_outline": 0.8,
    "dot_size":          30,
    "label_fontsize":    6.5,
    "title_fontsize":    18,
    "delay_label_offset": 0.35,
    "show_grid":         True,
    "scale_bar_length":  5.0,
    "fig_width":         11,
    "fig_height":        9,
    "view_orientation":  "top",
}

DEFAULT_CHARGE_PARAMS = {
    "stemming_multiplier":   20,
    "short_threshold":       4.0,
    "short_fixed":           1.5,
    "explosive_density_gcc": 1.15,
    "diameter_override_mm":  0,   # 0 = use XML diameter
}


def ring_key(base):
    """Sort key: B16_S6_R10 sorts after B16_S6_R9 (numeric on trailing number)."""
    import re
    m = re.search(r"R(\d+)(?:_|$)", base, re.IGNORECASE)
    return (int(m.group(1)) if m else 0, base)


def ring_label(base):
    """Return the compact ring identifier used in the top-view columns."""
    import re
    match = re.search(r"R(\d+)(?:_|$)", base, re.IGNORECASE)
    return f"R{int(match.group(1))}" if match else base


def batch_label(entries):
    """One stope/batch label for the whole batch (B27_S8_R1..R10 -> B27_S8).

    Input XML names are the primary source; a plan id ("B27 S8_R1") is used
    when a file name carries no stope information (e.g. a bare ``R3.XML``).
    """
    names = [stope_label_from_name(entry["base"]) or entry.get("plan_id") or ""
             for entry in entries]
    names = [name for name in names if str(name).strip()]
    return batch_stope_label(names)


def batch_artifact_names(stope, combined_name=None):
    """Final artifact file names for one batch (combined, top view, package)."""
    combined = combined_report_filename(
        combined_name or f"{stope}_Combined_RingBlast_Report"
    )
    return {
        "batch_label": stope,
        "combined_pdf": combined,
        "top_view_pdf": f"{stope}_Top_View_All_Rings.pdf",
        "package_zip": f"{stope}_RingBlast_Report_Package.zip",
    }


def custom_stemming_overrides(entry, start_ring, default_m=2.0,
                              depth_threshold_m=9.0, alternate_m=2.3):
    """Build deterministic per-hole stemming overrides for selected rings.

    Holes retain their XML order. Every hole receives ``default_m``; holes
    strictly deeper than the threshold alternate default/alternate, starting
    with the default value. Rings before ``start_ring`` remain untouched.
    """
    if ring_key(entry["base"])[0] < start_ring:
        return {}

    overrides = {}
    deep_hole_index = 0
    for hole in entry["holes"]:
        hole_key = hole.get("display") or hole["name"] or hole["id"]
        stemming_m = default_m
        if hole_length(hole) > depth_threshold_m:
            if deep_hole_index % 2:
                stemming_m = alternate_m
            deep_hole_index += 1
        overrides[hole_key] = stemming_m
    return overrides


def parse_batch(xml_files, collar_correction="off"):
    results = []
    for path in sorted(xml_files, key=lambda p: ring_key(os.path.splitext(os.path.basename(p))[0])):
        base = os.path.splitext(os.path.basename(path))[0]
        plan_name, plan_id, holes, segments = parse_xml(path, collar_correction=collar_correction)
        results.append({"base": base, "path": path, "plan_name": plan_name,
                        "plan_id": plan_id, "holes": holes, "segments": segments})
    return results


def build_report_pdf(entry, settings, charge_params, stemming_overrides=None):
    """One ring -> PDF bytes, charge CSV rows, totals (app's build_pdf_bytes)."""
    charge_data = build_charge_table(
        entry["holes"],
        stemming_overrides=stemming_overrides,
        stemming_multiplier=charge_params["stemming_multiplier"],
        short_threshold=charge_params["short_threshold"],
        short_fixed=charge_params["short_fixed"],
        explosive_density_gcc=charge_params["explosive_density_gcc"],
    )
    pdf = build_pdf_bytes(
        entry["plan_name"], entry["plan_id"], entry["holes"], entry["segments"],
        settings, charge_data, company="",
    )
    total_charge = sum(r["charge_kg"] for r in charge_data)
    return pdf, charge_data, total_charge


def build_top_view_grid(entries, settings, out_path):
    """Render one page of collar points in normalized, ring-labelled columns."""
    import re

    if not entries:
        raise ValueError("at least one ring is required for the top view")

    def ring_number(entry):
        match = re.search(r"R(\d+)(?:_|$)", entry["base"], re.IGNORECASE)
        return int(match.group(1)) if match else 0

    entries = sorted(entries, key=ring_number)
    numbers = [ring_number(entry) for entry in entries]
    cmap = matplotlib.colormaps["turbo"]
    norm = matplotlib.colors.Normalize(vmin=min(numbers), vmax=max(numbers) if len(set(numbers)) > 1 else min(numbers) + 1)

    fig, ax = plt.subplots(figsize=(16.5, 11.7))  # A3 landscape source image
    for column, entry in enumerate(entries, start=1):
        collars_x = [hole["x1"] for hole in entry["holes"]]
        collars_y = [hole["y1"] for hole in entry["holes"]]
        if not collars_x:
            continue
        xmin, xmax = min(collars_x), max(collars_x)
        ymin, ymax = min(collars_y), max(collars_y)
        xspan = xmax - xmin
        yspan = ymax - ymin
        local_x = [0.0 if xspan == 0 else (value - xmin) / xspan - 0.5 for value in collars_x]
        local_y = [0.5 if yspan == 0 else (value - ymin) / yspan for value in collars_y]
        display_x = [column + 0.55 * value for value in local_x]
        ax.scatter(
            display_x,
            local_y,
            color=cmap(norm(ring_number(entry))),
            s=max(35, settings.get("dot_size", 30)),
            edgecolors="black",
            linewidths=0.35,
            zorder=3,
        )
        ax.text(column, -0.10, ring_label(entry["base"]), ha="center", va="top", fontsize=13, fontweight="bold")

    prefix = entries[0]["base"].rsplit("_", 1)[0] if "_" in entries[0]["base"] else ""
    ring_range = f"R{numbers[0]} to R{numbers[-1]}"
    title = f"{prefix + ' — ' if prefix else ''}TOP VIEW — Rings {ring_range}"
    ax.set_title(title, fontsize=18, fontweight="bold", pad=18)
    ax.set_xlim(0.4, len(entries) + 0.6)
    ax.set_ylim(-0.18, 1.10)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor(settings.get("color_background", "#ffffff"))
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(
        0.02,
        0.02,
        "Each column is normalized to its ring's local collar bounding box",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color="#444444",
    )

    scalar = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array([])
    colorbar = fig.colorbar(scalar, ax=ax, fraction=0.025, pad=0.02, ticks=numbers)
    colorbar.set_label("Ring number")
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml", nargs="+", help="XML files (glob ok)")
    ap.add_argument("-o", "--output", default="generated_reports", help="output dir")
    ap.add_argument(
        "--combined-name",
        help="combined PDF name (default: <STOPE>_Combined_RingBlast_Report.pdf, "
             "with the stope label derived from the input XML names; "
             "invalid characters become underscores)",
    )
    ap.add_argument("--collar-correction", choices=["off", "auto"], default="off",
                    help="gallery-collar auto-correction (default off, matching the app)")
    ap.add_argument("--custom-stemming-from-ring", type=int,
                    help="first ring receiving deterministic custom stemming")
    ap.add_argument("--custom-stemming-default", type=float, default=2.0)
    ap.add_argument("--custom-stemming-depth-threshold", type=float, default=9.0)
    ap.add_argument("--custom-stemming-alternate", type=float, default=2.3)
    args = ap.parse_args()

    xml_files = []
    for pat in args.xml:
        xml_files.extend(glob.glob(pat))
    xml_files = sorted(set(os.path.abspath(p) for p in xml_files))
    if not xml_files:
        print("No XML files found.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    entries = parse_batch(xml_files, collar_correction=args.collar_correction)
    print(f"Parsed {len(entries)} XML(s)")

    stope = batch_label(entries)
    names = batch_artifact_names(stope, combined_name=args.combined_name)
    combined_filename = names["combined_pdf"]
    top_filename = names["top_view_pdf"]
    zip_filename = names["package_zip"]
    print(f"Batch label    : {stope}")

    settings = dict(DEFAULT_SETTINGS)
    charge_params = dict(DEFAULT_CHARGE_PARAMS)

    pdf_bytes, csv_bytes, summaries = {}, {}, []
    for e in entries:
        stemming_overrides = None
        if args.custom_stemming_from_ring is not None:
            stemming_overrides = custom_stemming_overrides(
                e,
                start_ring=args.custom_stemming_from_ring,
                default_m=args.custom_stemming_default,
                depth_threshold_m=args.custom_stemming_depth_threshold,
                alternate_m=args.custom_stemming_alternate,
            )
        pdf, charge_data, total_kg = build_report_pdf(
            e, settings, charge_params, stemming_overrides=stemming_overrides,
        )
        pdf_bytes[e["base"]] = pdf
        summaries.append({
            "ring": e["base"], "holes": len(charge_data),
            "total_charge_kg": round(total_kg, 2),
            "diameter_mm": charge_data[0]["diameter_mm"] if charge_data else None,
        })
        # CSV rows (same header as app)
        buf = io.StringIO()
        import csv
        writer = csv.writer(buf)
        writer.writerow(["Number", "Diameter (mm)", "Length (m)", "Actual meters",
                         "Stemming (m)", "Charge length (m)", "Charge (kg)",
                         "Actual charge", "Delay (ms)"])
        for r in charge_data:
            writer.writerow([r["hole_key"], f"{r['diameter_mm']:.0f}", f"{r['depth_m']:.3f}",
                             "", f"{r['stemming_m']:.2f}", f"{r['charge_length_m']:.2f}",
                             f"{r['charge_kg']:.2f}", "", r["delay_ms"] if r["delay_ms"] != "" else ""])
        csv_bytes[e["base"]] = buf.getvalue().encode()

    # 1) Combined PDF (all rings, one file)
    combined = merge_pdf_bytes(pdf_bytes[e["base"]] for e in entries)
    combined_path = os.path.join(args.output, combined_filename)
    with open(combined_path, "wb") as f:
        f.write(combined)

    # 2) Single-page top view of all rings
    top_path = os.path.join(args.output, top_filename)
    png_tmp = os.path.join(args.output, "_top_view_all_rings.png")
    build_top_view_grid(entries, settings, png_tmp)
    # embed PNG into a one-page A3 landscape PDF
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(top_path, pagesize=landscape(A3))
    W, H = landscape(A3)
    img = ImageReader(png_tmp)
    iw, ih = img.getSize()
    margin = 14
    scale = min((W - 2 * margin) / iw, (H - 2 * margin) / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(img, (W - dw) / 2, (H - dh) / 2, width=dw, height=dh,
                preserveAspectRatio=True, anchor="c")
    c.showPage()
    c.save()

    # 3) Individual PDFs + CSVs + combined + top view + summary -> ZIP package
    zip_path = os.path.join(args.output, zip_filename)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(combined_path, f"reports_pdf/{combined_filename}")
        for e in entries:
            zf.writestr(f"reports_pdf/{e['base']}_blast_report.pdf", pdf_bytes[e["base"]])
            zf.writestr(f"csv/{e['base']}_charge.csv", csv_bytes[e["base"]])
        zf.writestr(f"top_view/{top_filename}", open(top_path, "rb").read())
        zf.writestr("generation_summary.json", json.dumps({
            "source_zip": os.path.basename(args.xml[0]).split(".")[0],
            "source_files": [os.path.basename(e["path"]) for e in entries],
            "source_count": len(entries),
            "batch_label": stope,
            "combined_pdf": combined_filename,
            "artifact_names": {
                "batch_label": stope,
                "combined_pdf": combined_filename,
                "top_view_pdf": top_filename,
                "package_zip": zip_filename,
                "zip_combined_entry": f"reports_pdf/{combined_filename}",
                "zip_top_view_entry": f"top_view/{top_filename}",
                "per_ring_reports": [f"reports_pdf/{e['base']}_blast_report.pdf" for e in entries],
                "per_ring_csvs": [f"csv/{e['base']}_charge.csv" for e in entries],
                "summary": "generation_summary.json",
            },
            "rings": summaries,
            "settings": settings,
            "charge_params": charge_params,
            "collar_correction": args.collar_correction,
            "custom_stemming": (
                {
                    "from_ring": args.custom_stemming_from_ring,
                    "default_m": args.custom_stemming_default,
                    "depth_strictly_greater_than_m": args.custom_stemming_depth_threshold,
                    "alternating_m": [args.custom_stemming_default, args.custom_stemming_alternate],
                    "order": "source XML hole order; first qualifying hole uses default_m",
                }
                if args.custom_stemming_from_ring is not None else None
            ),
        }, indent=2))

    # Summary table
    print(f"\n{'ring':<16}{'holes':>6}{'charge kg':>12}")
    for s in summaries:
        print(f"{s['ring']:<16}{s['holes']:>6}{s['total_charge_kg']:>12.2f}")
    print(f"\nBatch label    : {stope}")
    print(f"Combined PDF   : {combined_filename} -> {combined_path} ({os.path.getsize(combined_path)} bytes)")
    print(f"Top view PDF   : {top_filename} -> {top_path} ({os.path.getsize(top_path)} bytes)")
    print(f"Package ZIP    : {zip_filename} -> {zip_path} ({os.path.getsize(zip_path)} bytes)")
    print(f"Per-ring PDFs  : reports_pdf/{stope}_R*_blast_report.pdf ({len(entries)} in ZIP)")
    print(f"Per-ring CSVs  : csv/{stope}_R*_charge.csv ({len(entries)} in ZIP)")
    print(f"Summary JSON   : generation_summary.json (inside {zip_filename})")


if __name__ == "__main__":
    main()
