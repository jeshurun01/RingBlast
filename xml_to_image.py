"""
xml_to_image.py — Generate PNG drill plan images directly from iRedes DRPPlan XML files.

Usage:
    python3 xml_to_image.py            # processes all *.XML files in the current directory
    python3 xml_to_image.py FILE.XML   # process a specific file

Output: images/{base_name}.png
"""

import xml.etree.ElementTree as ET
import csv
import glob
import os
import sys
import math
import matplotlib
matplotlib.use("Agg")  # non-interactive backend; no display required
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import FancyArrowPatch
from matplotlib.gridspec import GridSpec

# ── Namespaces ──────────────────────────────────────────────────────────────────
NS = {
    "drp": "http://www.iredes.org/xml/DrillRig",
    "ir":  "http://www.iredes.org/xml",
}

# ── Visual style constants ───────────────────────────────────────────────────────
COLOR_HOLE    = "#000000"
COLOR_OUTLINE = "#000000"
COLOR_DOT     = "#000000"
LINEWIDTH_HOLE    = 0.8
LINEWIDTH_OUTLINE = 0.8
DOT_SIZE      = 30
LABEL_FONTSIZE = 6.5
TITLE_FONTSIZE = 18
OUTPUT_DPI    = 150
OUTPUT_DIR    = "images"
CSV_OUTPUT_DIR = "depth_output"

# ── Charging defaults ────────────────────────────────────────────────────────────
STEMMING_MULTIPLIER       = 20    # x (diameter_mm / 1000) -> stemming in metres
SHORT_HOLE_THRESHOLD      = 4.0   # m -- holes shorter than this use the special rule
SHORT_HOLE_FIXED_STEMMING = 1.5   # m -- fixed stemming for short holes (or depth/2 if smaller)
EXPLOSIVE_DENSITY_GCC     = 1.15  # g/cc
COLOR_CHARGE              = "#cc0000"  # red charge overlay line


# ── XML Parsing ─────────────────────────────────────────────────────────────────

def _text(elem, tag):
    child = elem.find(tag, NS)
    return child.text if child is not None else None


def parse_xml(xml_source, filename=None):
    """Parse xml_source (file path string or file-like object)."""
    tree = ET.parse(xml_source)
    root = tree.getroot()

    if filename is None:
        filename = xml_source if isinstance(xml_source, str) else "plan"
    default_name = os.path.splitext(os.path.basename(filename))[0]
    plan_name = _text(root, ".//ir:PlanName") or default_name
    plan_id   = _text(root, ".//ir:PlanId")   or plan_name

    holes = []
    for hole in root.findall(".//drp:Hole", NS):
        sp = hole.find("drp:StartPoint", NS)
        ep = hole.find("drp:EndPoint",   NS)
        if sp is None or ep is None:
            continue

        x1 = float(_text(sp, "ir:PointX"))
        y1 = float(_text(sp, "ir:PointY"))
        x2 = float(_text(ep, "ir:PointX"))
        y2 = float(_text(ep, "ir:PointY"))

        drill_dia = float(_text(hole, "drp:DrillBitDia") or 0)
        if drill_dia == 0:
            continue

        hole_id   = _text(hole, "drp:HoleId")   or ""
        hole_name = _text(hole, "drp:HoleName") or ""
        distance  = math.hypot(x2 - x1, y2 - y1)
        label = f"{hole_name}_{distance:.3f}" if hole_name else f"H{hole_id}_{distance:.3f}"

        holes.append({
            "id": hole_id, "name": hole_name, "label": label,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "diameter_mm": drill_dia,
        })

    segments = []
    for line in root.findall(".//drp:Line", NS):
        sp = line.find("ir:StartPoint", NS)
        ep = line.find("ir:EndPoint",   NS)
        if sp is None or ep is None:
            continue
        x1 = float(_text(sp, "ir:PointX"))
        y1 = float(_text(sp, "ir:PointY"))
        x2 = float(_text(ep, "ir:PointX"))
        y2 = float(_text(ep, "ir:PointY"))
        segments.append((x1, y1, x2, y2))

    return plan_name, plan_id, holes, segments


# ── Stemming & charge calculations ──────────────────────────────────────────────

def compute_stemming(depth_m, diameter_mm,
                     multiplier=STEMMING_MULTIPLIER,
                     short_threshold=SHORT_HOLE_THRESHOLD,
                     short_fixed=SHORT_HOLE_FIXED_STEMMING):
    """Return stemming length in metres for a single hole."""
    if depth_m < short_threshold:
        return min(short_fixed, depth_m / 2.0)
    return min(diameter_mm / 1000.0 * multiplier, depth_m / 2.0)


def build_charge_table(holes, stemming_overrides=None, delay_map=None,
                        diameter_overrides=None,
                        stemming_multiplier=STEMMING_MULTIPLIER,
                        short_threshold=SHORT_HOLE_THRESHOLD,
                        short_fixed=SHORT_HOLE_FIXED_STEMMING,
                        explosive_density_gcc=EXPLOSIVE_DENSITY_GCC):
    """Compute per-hole charge data.

    Parameters
    ----------
    holes              : list of hole dicts from parse_xml()
    stemming_overrides : dict {hole_key: stemming_m} -- overrides auto-calculation
    diameter_overrides : dict {hole_key: diameter_mm} -- overrides XML diameter
    delay_map          : dict {hole_key: delay_ms}

    Returns
    -------
    list of dicts with keys:
        hole_key, diameter_mm, depth_m, stemming_m, charge_length_m,
        charge_kg, delay_ms, x1, y1, x2, y2
    """
    if stemming_overrides is None:
        stemming_overrides = {}
    if diameter_overrides is None:
        diameter_overrides = {}
    if delay_map is None:
        delay_map = {}

    rows = []
    for h in holes:
        hole_key    = h["name"] or h["id"]
        depth_m     = math.hypot(h["x2"] - h["x1"], h["y2"] - h["y1"])
        diameter_mm = diameter_overrides.get(hole_key, h.get("diameter_mm", 89.0))

        override = stemming_overrides.get(hole_key)
        try:
            stemming_m = float(override)
            if math.isnan(stemming_m):
                raise ValueError
        except (TypeError, ValueError):
            stemming_m = compute_stemming(depth_m, diameter_mm,
                                          stemming_multiplier, short_threshold, short_fixed)

        charge_length_m = max(0.0, depth_m - stemming_m)
        radius_m        = diameter_mm / 2000.0
        charge_kg       = charge_length_m * math.pi * radius_m ** 2 * explosive_density_gcc * 1000.0

        delay_raw = delay_map.get(hole_key, "")
        try:
            delay_ms = int(float(delay_raw)) if str(delay_raw).strip() not in ("", "nan") else ""
        except (TypeError, ValueError):
            delay_ms = ""

        rows.append({
            "hole_key":        hole_key,
            "diameter_mm":     diameter_mm,
            "depth_m":         depth_m,
            "stemming_m":      round(stemming_m, 3),
            "charge_length_m": round(charge_length_m, 3),
            "charge_kg":       round(charge_kg, 2),
            "delay_ms":        delay_ms,
            "x1": h["x1"], "y1": h["y1"],
            "x2": h["x2"], "y2": h["y2"],
        })
    return rows


# ── Scale bar ───────────────────────────────────────────────────────────────────

def _draw_scale_bar(ax, x_left, y_bottom, bar_length=5.0):
    y_bar   = y_bottom
    y_label = y_bottom + (bar_length * 0.10)
    mid     = x_left + bar_length / 2

    ax.fill_between([x_left, mid], y_bar - bar_length * 0.025, y_bar,
                    color="black", zorder=5)
    ax.fill_between([mid, x_left + bar_length], y_bar - bar_length * 0.025, y_bar,
                    color="white", edgecolor="black", linewidth=0.8, zorder=5)
    ax.plot([x_left, mid], [y_bar - bar_length * 0.025, y_bar - bar_length * 0.025],
            color="black", linewidth=0.8, zorder=6)
    ax.plot([x_left, x_left], [y_bar - bar_length * 0.025, y_bar],
            color="black", linewidth=0.8, zorder=6)

    for x_pos, txt in [(x_left, "0"), (mid, f"{bar_length / 2:g}"),
                        (x_left + bar_length, f"{bar_length:g} m")]:
        ax.text(x_pos, y_label, txt, ha="center", va="bottom", fontsize=7, zorder=7)


# ── Core drawing helper ──────────────────────────────────────────────────────────

def _draw_plan_on_ax(ax, plan_id, holes, segments, settings, charge_data=None):
    """Draw the drill plan (+ optional charge overlay) onto an existing axes."""
    c_hole   = settings.get("color_hole",        COLOR_HOLE)
    c_out    = settings.get("color_outline",     COLOR_OUTLINE)
    c_dot    = settings.get("color_dot",         COLOR_DOT)
    c_bg     = settings.get("color_background",  "#ffffff")
    c_charge = settings.get("color_charge",      COLOR_CHARGE)
    lw_hole  = settings.get("linewidth_hole",    LINEWIDTH_HOLE)
    lw_out   = settings.get("linewidth_outline", LINEWIDTH_OUTLINE)
    dot_sz   = settings.get("dot_size",          DOT_SIZE)
    lbl_fs   = settings.get("label_fontsize",    LABEL_FONTSIZE)
    ttl_fs   = settings.get("title_fontsize",    TITLE_FONTSIZE)
    grid_on  = settings.get("show_grid",         True)
    bar_len  = settings.get("scale_bar_length",  5.0)

    title_parts = plan_id.replace("_", " ").replace("-", " - ").split()
    title = " ".join(p.capitalize() if p.isalpha() else p for p in title_parts)

    ax.set_aspect("equal")
    ax.set_facecolor(c_bg)
    if grid_on:
        ax.grid(True, linestyle="--", linewidth=0.4, color="#cccccc", alpha=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_edgecolor("#cccccc")

    # Contour outline
    for x1, y1, x2, y2 in segments:
        ax.plot([x1, x2], [y1, y2], color=c_out,
                linewidth=lw_out, solid_capstyle="round", zorder=2)

    # Charge lookup
    charge_lookup = {row["hole_key"]: row for row in charge_data} if charge_data else {}

    # Drill holes
    for h in holes:
        ax.plot([h["x1"], h["x2"]], [h["y1"], h["y2"]],
                color=c_hole, linewidth=lw_hole, solid_capstyle="round", zorder=3)
        ax.scatter([h["x1"], h["x2"]], [h["y1"], h["y2"]],
                   color=c_dot, s=dot_sz, zorder=4, linewidths=0)

        mx = (h["x1"] + h["x2"]) / 2
        my = (h["y1"] + h["y2"]) / 2
        dx = h["x2"] - h["x1"]
        dy = h["y2"] - h["y1"]
        angle = math.degrees(math.atan2(dy, dx))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        ax.text(mx, my, h["label"],
                rotation=angle, rotation_mode="anchor",
                ha="center", va="bottom",
                fontsize=lbl_fs, zorder=5, color="#111111")

        # Charge overlay + delay label
        hole_key = h["name"] or h["id"]
        crow = charge_lookup.get(hole_key)
        if crow:
            depth  = crow["depth_m"]
            ch_len = crow["charge_length_m"]
            if ch_len > 0 and depth > 0:
                ratio = ch_len / depth
                # Charge runs from toe (x2,y2) toward collar (x1,y1)
                cx = h["x2"] + (h["x1"] - h["x2"]) * ratio
                cy = h["y2"] + (h["y1"] - h["y2"]) * ratio
                ax.plot([h["x2"], cx], [h["y2"], cy],
                        color=c_charge, linewidth=lw_hole * 2.0,
                        solid_capstyle="round", zorder=3.5)

            delay = crow.get("delay_ms", "")
            if delay not in ("", None) and str(delay).strip() not in ("", "nan"):
                if depth > 0:
                    ux = (h["x2"] - h["x1"]) / depth
                    uy = (h["y2"] - h["y1"]) / depth
                    px, py = -uy, ux  # perpendicular (90 deg CCW)
                    # Configurable perpendicular offset for the delay label
                    offset = settings.get("delay_label_offset", 0.35)
                    lx = h["x2"] + px * offset
                    ly = h["y2"] + py * offset
                    dl_angle = math.degrees(math.atan2(uy, ux))
                    if dl_angle > 90:
                        dl_angle -= 180
                    elif dl_angle < -90:
                        dl_angle += 180
                    ax.text(lx, ly, f"{delay} ms",
                            rotation=dl_angle, rotation_mode="anchor",
                            ha="center", va="bottom",
                            fontsize=lbl_fs * 0.9, zorder=6, color="#0044aa")

    if settings.get("show_title", True):
        ax.set_title(title, fontsize=ttl_fs, pad=12, fontweight="normal")

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    margin_x = (xlim[1] - xlim[0]) * 0.03
    margin_y = (ylim[1] - ylim[0]) * 0.03
    _draw_scale_bar(ax,
                    x_left=xlim[0] + margin_x,
                    y_bottom=ylim[0] + margin_y,
                    bar_length=bar_len)


# ── Figure builder ───────────────────────────────────────────────────────────────

def build_figure(plan_name, plan_id, holes, segments, settings, charge_data=None):
    """Render a drill plan to a matplotlib Figure.

    charge_data : optional list from build_charge_table() -- draws red charge lines
                  and blue delay labels when supplied.

    Returns (fig, csv_rows)  where csv_rows = [[hole_id, depth_str], ...]
    """
    fw   = settings.get("fig_width",        11)
    fh   = settings.get("fig_height",       9)
    c_bg = settings.get("color_background", "#ffffff")

    fig, ax = plt.subplots(figsize=(fw, fh))
    fig.patch.set_facecolor(c_bg)
    _draw_plan_on_ax(ax, plan_id, holes, segments, settings, charge_data)

    csv_rows = []
    for h in holes:
        depth = math.hypot(h["x2"] - h["x1"], h["y2"] - h["y1"])
        csv_rows.append([h["name"] or h["id"], f"{depth:.3f}"])
    return fig, csv_rows


# ── Report figure: drill plan + charge table combined ────────────────────────────

def build_report_figure(plan_name, plan_id, holes, segments, settings, charge_data):
    """Build a combined PNG: drill plan (top) + charge table (bottom).

    Returns (fig, report_csv_rows)
    """
    fw      = settings.get("fig_width",        11)
    fh_plan = settings.get("fig_height",       9)
    c_bg    = settings.get("color_background", "#ffffff")

    n = len(charge_data)
    fh_table = max(2.5, (n + 2) * 0.30)

    fig = plt.figure(figsize=(fw, fh_plan + fh_table))
    fig.patch.set_facecolor(c_bg)
    gs = GridSpec(2, 1, figure=fig, height_ratios=[fh_plan, fh_table], hspace=0.05)
    ax_plan  = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    _draw_plan_on_ax(ax_plan, plan_id, holes, segments, settings, charge_data)

    col_labels = [
        "Number", "O (mm)", "Length (m)", "Act. meters",
        "Stemming (m)", "Ch. length (m)", "Charge (kg)", "Act. charge", "Delay (ms)"
    ]
    cell_text = []
    report_csv_rows = []
    for row in charge_data:
        delay_str = (f"{row['delay_ms']} ms"
                     if row["delay_ms"] not in ("", None) else "")
        cell_text.append([
            row["hole_key"],
            f"{row['diameter_mm']:.0f}",
            f"{row['depth_m']:.3f}",
            "",
            f"{row['stemming_m']:.2f}",
            f"{row['charge_length_m']:.2f}",
            f"{row['charge_kg']:.2f}",
            "",
            delay_str,
        ])
        report_csv_rows.append([
            row["hole_key"], f"{row['diameter_mm']:.0f}", f"{row['depth_m']:.3f}",
            "", f"{row['stemming_m']:.2f}", f"{row['charge_length_m']:.2f}",
            f"{row['charge_kg']:.2f}", "", delay_str,
        ])

    total_charge = sum(r["charge_kg"] for r in charge_data)
    cell_text.append(["", "", "", "", "", "Total Charge",
                       f"{total_charge:.2f} kg", "", ""])

    ax_table.axis("off")
    tbl = ax_table.table(
        cellText=cell_text,
        colLabels=col_labels,
        cellLoc="center",
        loc="upper center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1, 1.4)

    ncols = len(col_labels)
    for c in range(ncols):
        cell = tbl[(0, c)]
        cell.set_facecolor("#dce3ec")
        cell.set_text_props(fontweight="bold")
    for r in range(1, n + 1):
        shade = "#f7f7f7" if r % 2 == 0 else "#ffffff"
        for c in range(ncols):
            tbl[(r, c)].set_facecolor(shade)
    for c in range(ncols):
        cell = tbl[(n + 1, c)]
        cell.set_facecolor("#fffde7")
        cell.set_text_props(fontweight="bold")

    return fig, report_csv_rows


# ── PDF report ───────────────────────────────────────────────────────────────────

def build_pdf_bytes(plan_name, plan_id, holes, segments, settings, charge_data, company=""):
    """Build a print-ready A4 portrait PDF blast report.

    Layout — page 1:
        header  → info box (hole ⌀ / count) → plan image (fills remaining space,
        centred) → charge table pinned to the bottom margin.

    Continuation pages (if rows overflow page 1):
        header → table rows → totals on last page.

    Returns raw PDF bytes.
    """
    # ── Lazy imports so the CLI works without reportlab ──────────────────────
    import datetime
    import os
    from io import BytesIO as _BytesIO

    from reportlab.lib import colors as rl_colors
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Table, TableStyle

    # ── A4 portrait constants ────────────────────────────────────────────────
    PAGE_W    = 595.28
    PAGE_H    = 841.89
    MARGIN    = 15.0
    CONTENT_W = PAGE_W - 2.0 * MARGIN

    HEADER_H  = 68.0    # three-column logo header
    LOGO_W    = 155.0
    GAP       = 7.0
    INFO_H    = 30.0    # reduced: 2 compact rows
    ROW_H     = 14.5    # table row height
    MIN_PLAN_H = 200.0  # never shrink the plan image below this

    # ── Logo paths ────────────────────────────────────────────────────────────
    _here      = os.path.dirname(os.path.abspath(__file__))
    _logo_dir  = os.path.join(_here, "logos")
    AECI_LOGO  = os.path.join(_logo_dir, "aeci-mining-explosives-south-africa-logo.png")
    KAMOA_LOGO = os.path.join(_logo_dir, "Kamoa_LOGO.png")

    # ── Table column definitions ──────────────────────────────────────────────
    COL_LABELS = [
        "Number", "\u00d8 (mm)", "Length (m)", "Act. meters",
        "Stemming (m)", "Ch. length (m)", "Charge (kg)", "Act. charge", "Delay (ms)",
    ]
    _cw = [38, 42, 60, 68, 58, 63, 56, 68]
    COL_WIDTHS = _cw + [CONTENT_W - sum(_cw)]

    all_data_rows = []
    for row in charge_data:
        delay_str = (f"{row['delay_ms']} ms" if row["delay_ms"] not in ("", None) else "")
        all_data_rows.append([
            row["hole_key"],
            f"{row['diameter_mm']:.0f}",
            f"{row['depth_m']:.3f}",
            "",
            f"{row['stemming_m']:.2f}",
            f"{row['charge_length_m']:.2f}",
            f"{row['charge_kg']:.2f}",
            "",
            delay_str,
        ])
    total_charge = sum(r["charge_kg"] for r in charge_data)
    TOTALS_ROW   = ["", "", "", "", "", "Total Charge", f"{total_charge:.2f} kg", "", ""]

    # ── Page 1: compute dynamic plan height ───────────────────────────────────
    # Available height below the info box on page 1:
    #   PAGE_H - MARGIN(top) - HEADER_H - GAP - INFO_H - GAP
    #         - GAP(above image) - PLAN_H - GAP(between image & table)
    #         - TABLE_H - MARGIN(bottom)
    # We want: PLAN_H as large as possible while keeping TABLE_H = all rows.
    # If that makes PLAN_H < MIN_PLAN_H we paginate the table instead.

    _below_info_avail = PAGE_H - MARGIN - HEADER_H - GAP - INFO_H - GAP - MARGIN
    tbl_h_all = (len(all_data_rows) + 2) * ROW_H  # header row + data + totals
    plan_h_if_all = _below_info_avail - 2 * GAP - tbl_h_all

    if plan_h_if_all >= MIN_PLAN_H:
        PLAN_H  = plan_h_if_all
        pages   = [[COL_LABELS] + all_data_rows + [TOTALS_ROW]]
    else:
        PLAN_H  = MIN_PLAN_H
        _max_tbl_h_p1 = _below_info_avail - 2 * GAP - PLAN_H
        max_rows_p1   = max(5, int(_max_tbl_h_p1 / ROW_H) - 2)
        _overhead_pN  = MARGIN + HEADER_H + GAP + MARGIN
        max_rows_pN   = max(5, int((PAGE_H - _overhead_pN) / ROW_H) - 2)

        pages = [[COL_LABELS] + all_data_rows[:max_rows_p1] + [TOTALS_ROW]]
        remaining = all_data_rows[max_rows_p1:]
        while remaining:
            chunk, remaining = remaining[:max_rows_pN], remaining[max_rows_pN:]
            pages.append([COL_LABELS] + chunk + ([TOTALS_ROW] if not remaining else []))

    # ── Render plan PNG (no title — already shown in header) ─────────────────
    _ps = dict(settings)
    _ps["fig_width"]   = CONTENT_W / 72.0
    _ps["fig_height"]  = PLAN_H    / 72.0
    _ps["show_title"]  = False          # title is in the PDF header, not the image
    _fig, _ = build_figure(plan_name, plan_id, holes, segments, _ps, charge_data)
    _plan_buf = _BytesIO()
    _fig.savefig(_plan_buf, format="png", dpi=150, bbox_inches="tight",
                 facecolor=_fig.get_facecolor())
    _plan_buf.seek(0)
    plt.close(_fig)
    plan_img = ImageReader(_plan_buf)

    # ── Colour helpers ────────────────────────────────────────────────────────
    def _c(h):
        h = h.lstrip("#")
        return rl_colors.Color(int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255)

    C_BG       = _c(settings.get("color_background", "#ffffff"))
    C_HDR_CELL = _c("#dce3ec")
    C_ACT_HDR  = _c("#b8cce4")
    C_ACT_DATA = _c("#eef3fc")
    C_EVEN     = _c("#f7f7f7")
    C_ODD      = rl_colors.white
    C_TOTALS   = _c("#fffde7")
    C_GRID     = _c("#aaaaaa")
    C_BORDER   = _c("#888888")

    def _table_style(tbl_rows):
        n_data = len(tbl_rows) - 2
        cmds = [
            ("FONTSIZE",      (0, 0), (-1, -1),   7.5),
            ("VALIGN",        (0, 0), (-1, -1),   "MIDDLE"),
            ("ALIGN",         (0, 0), (-1, -1),   "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1),   1),
            ("BOTTOMPADDING", (0, 0), (-1, -1),   1),
            ("GRID",          (0, 0), (-1, -1),   0.4, C_GRID),
            ("BACKGROUND",    (0, 0), (-1, 0),    C_HDR_CELL),
            ("FONTNAME",      (0, 0), (-1, 0),    "Helvetica-Bold"),
            ("BACKGROUND",    (3, 0), (3, 0),     C_ACT_HDR),
            ("BACKGROUND",    (7, 0), (7, 0),     C_ACT_HDR),
            ("FONTNAME",      (0, 1), (-1, -2),   "Helvetica"),
            ("BACKGROUND",    (0, -1), (-1, -1),  C_TOTALS),
            ("FONTNAME",      (0, -1), (-1, -1),  "Helvetica-Bold"),
        ]
        for r in range(1, n_data + 1):
            cmds.append(("BACKGROUND", (0, r), (-1, r), C_EVEN if r % 2 == 0 else C_ODD))
            cmds.append(("BACKGROUND", (3, r), (3, r), C_ACT_DATA))
            cmds.append(("BACKGROUND", (7, r), (7, r), C_ACT_DATA))
        return TableStyle(cmds)

    # ── Info box values ───────────────────────────────────────────────────────
    _dia_val = f"{charge_data[0]['diameter_mm']:.0f}" if charge_data else "\u2014"
    _n_holes = str(len(charge_data))

    # ── Draw pages ────────────────────────────────────────────────────────────
    buf   = _BytesIO()
    c     = rl_canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    today = datetime.date.today().strftime("%Y-%m-%d")

    for page_idx, tbl_rows in enumerate(pages):
        is_first = (page_idx == 0)

        c.setFillColor(C_BG)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        # ── Logo header ───────────────────────────────────────────────────────
        hdr_y = PAGE_H - MARGIN - HEADER_H
        _lp   = 6

        c.setFillColor(rl_colors.white)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.8)
        c.rect(MARGIN, hdr_y, CONTENT_W, HEADER_H, fill=1, stroke=1)
        c.line(MARGIN + LOGO_W,          hdr_y, MARGIN + LOGO_W,          hdr_y + HEADER_H)
        c.line(PAGE_W - MARGIN - LOGO_W, hdr_y, PAGE_W - MARGIN - LOGO_W, hdr_y + HEADER_H)

        if os.path.exists(AECI_LOGO):
            c.drawImage(AECI_LOGO, MARGIN + _lp, hdr_y + _lp,
                        width=LOGO_W - 2*_lp, height=HEADER_H - 2*_lp,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        else:
            c.setFont("Helvetica-Bold", 9); c.setFillColor(rl_colors.HexColor("#555555"))
            c.drawCentredString(MARGIN + LOGO_W/2, hdr_y + HEADER_H/2 - 5, "AECI")

        centre_x  = MARGIN + LOGO_W + (CONTENT_W - 2*LOGO_W) / 2
        plan_title = plan_id.replace("_", " ").replace("-", " \u2013 ")
        c.setFillColor(rl_colors.HexColor("#111111"))
        c.setFont("Helvetica-Bold", 15)
        title_y = hdr_y + HEADER_H/2 - 5 if not company else hdr_y + HEADER_H/2
        c.drawCentredString(centre_x, title_y, plan_title)
        if company:
            c.setFont("Helvetica", 8); c.setFillColor(rl_colors.HexColor("#666666"))
            c.drawCentredString(centre_x, hdr_y + 9, company)

        rx = PAGE_W - MARGIN - LOGO_W
        if os.path.exists(KAMOA_LOGO):
            c.drawImage(KAMOA_LOGO, rx + _lp, hdr_y + _lp,
                        width=LOGO_W - 2*_lp, height=HEADER_H - 2*_lp,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        else:
            c.setFont("Helvetica-Bold", 9); c.setFillColor(rl_colors.HexColor("#555555"))
            c.drawCentredString(rx + LOGO_W/2, hdr_y + HEADER_H/2 - 5, "KAMOA COPPER")

        c.setFont("Helvetica", 7); c.setFillColor(rl_colors.HexColor("#888888"))
        c.drawRightString(PAGE_W - MARGIN - _lp, hdr_y + 4, today)

        below_hdr = hdr_y - GAP

        if is_first:
            # ── Info summary box (compact) ────────────────────────────────────
            _iw    = 230.0
            _irh   = INFO_H / 2
            _val_w = 55.0
            c.setLineWidth(0.4); c.setStrokeColor(C_BORDER)
            for i, (lbl, val) in enumerate(
                [("Hole diameter (mm)", _dia_val), ("Number of holes", _n_holes)]
            ):
                iy = below_hdr - (i + 1) * _irh
                c.setFillColor(_c("#f0f0f0") if i % 2 == 0 else rl_colors.white)
                c.rect(MARGIN, iy, _iw - _val_w, _irh, fill=1, stroke=1)
                c.setFillColor(rl_colors.HexColor("#111111"))
                c.setFont("Helvetica", 8)
                c.drawString(MARGIN + 4, iy + _irh/2 - 4, lbl)
                c.setFillColor(rl_colors.white)
                c.rect(MARGIN + _iw - _val_w, iy, _val_w, _irh, fill=1, stroke=1)
                c.setFillColor(rl_colors.HexColor("#111111"))
                c.setFont("Helvetica-Bold", 9)
                c.drawCentredString(MARGIN + _iw - _val_w/2, iy + _irh/2 - 4, val)

            # ── Table pinned to bottom ────────────────────────────────────────
            n_tbl = len(tbl_rows)
            tbl_h = n_tbl * ROW_H
            tbl_bottom = MARGIN                     # table sits on the bottom margin
            tbl_top    = tbl_bottom + tbl_h

            # ── Plan image: fills space between info box and table ────────────
            plan_bottom = tbl_top + GAP
            plan_top    = below_hdr - INFO_H - GAP
            actual_plan_h = plan_top - plan_bottom  # may differ from PLAN_H due to rounding

            # Draw centred: bounding box = full content width, anchor="c"
            c.drawImage(plan_img,
                        MARGIN, plan_bottom,
                        width=CONTENT_W, height=actual_plan_h,
                        preserveAspectRatio=True, anchor="c")
        else:
            # Continuation pages: table fills available space below header
            n_tbl = len(tbl_rows)
            tbl_h = n_tbl * ROW_H
            tbl_bottom = MARGIN
            tbl_top    = below_hdr   # unused, but kept for clarity

        # ── Charge table ──────────────────────────────────────────────────────
        tbl = Table(tbl_rows, colWidths=COL_WIDTHS, rowHeights=ROW_H)
        tbl.setStyle(_table_style(tbl_rows))
        tbl.wrapOn(c, CONTENT_W, tbl_h)
        tbl.drawOn(c, MARGIN, tbl_bottom)

        if len(pages) > 1:
            c.setFont("Helvetica", 7); c.setFillColor(rl_colors.HexColor("#888888"))
            c.drawRightString(PAGE_W - MARGIN, MARGIN / 2,
                              f"Page {page_idx + 1} of {len(pages)}")
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


# ── CLI render ───────────────────────────────────────────────────────────────────

def render(xml_file, output_dir=OUTPUT_DIR, csv_output_dir=CSV_OUTPUT_DIR):
    plan_name, plan_id, holes, segments = parse_xml(xml_file)

    settings = {
        "color_hole":        COLOR_HOLE,
        "color_outline":     COLOR_OUTLINE,
        "color_dot":         COLOR_DOT,
        "color_background":  "#ffffff",
        "linewidth_hole":    LINEWIDTH_HOLE,
        "linewidth_outline": LINEWIDTH_OUTLINE,
        "dot_size":          DOT_SIZE,
        "label_fontsize":    LABEL_FONTSIZE,
        "title_fontsize":    TITLE_FONTSIZE,
        "show_grid":         True,
        "scale_bar_length":  5.0,
        "fig_width":         11,
        "fig_height":        9,
    }

    fig, csv_rows = build_figure(plan_name, plan_id, holes, segments, settings)

    os.makedirs(output_dir, exist_ok=True)
    base_name   = os.path.splitext(os.path.basename(xml_file))[0]
    output_path = os.path.join(output_dir, f"{base_name}.png")
    fig.savefig(output_path, dpi=OUTPUT_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Saved -> {output_path}")

    os.makedirs(csv_output_dir, exist_ok=True)
    csv_path = os.path.join(csv_output_dir, f"{base_name}_depth.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hole_id", "hole_depth"])
        writer.writerows(csv_rows)
    print(f"  Saved -> {csv_path}")

    return output_path


# ── Entry point ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        xml_files = sys.argv[1:]
    else:
        xml_files = sorted(glob.glob("*.XML"))

    if not xml_files:
        print("No XML files found.")
        sys.exit(1)

    print(f"Processing {len(xml_files)} file(s)...")
    for xml_file in xml_files:
        if not os.path.isfile(xml_file):
            print(f"  Skipping -- file not found: {xml_file}")
            continue
        try:
            render(xml_file)
        except Exception as exc:
            print(f"  ERROR processing {xml_file}: {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
