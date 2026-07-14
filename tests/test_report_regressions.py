import io

from pypdf import PdfReader

from app_utils import csv_safe_cell, safe_upload_base, unique_upload_base, upload_fingerprint
from xml_to_image import build_charge_table, build_pdf_bytes, parse_xml


SETTINGS = {
    "color_hole": "#000000",
    "color_outline": "#000000",
    "color_dot": "#000000",
    "color_background": "#ffffff",
    "color_charge": "#cc0000",
    "linewidth_hole": 0.8,
    "linewidth_outline": 0.8,
    "dot_size": 30,
    "label_fontsize": 6.5,
    "title_fontsize": 18,
    "show_grid": True,
    "scale_bar_length": 5.0,
    "fig_width": 11,
    "fig_height": 9,
}


def _many_holes(count=80):
    holes = []
    for i in range(count):
        x = float(i % 10)
        holes.append({
            "id": str(i + 1),
            "name": f"H{i + 1}",
            "display": f"H{i + 1}",
            "label": f"H{i + 1} 10.000",
            "x1": x,
            "y1": 0.0,
            "x2": x,
            "y2": 10.0,
            "diameter_mm": 89.0,
        })
    return holes


def test_paginated_pdf_contains_grand_total_exactly_once():
    holes = _many_holes()
    charge_data = build_charge_table(holes)

    pdf = build_pdf_bytes("Large plan", "LARGE_PLAN", holes, [], SETTINGS, charge_data)
    reader = PdfReader(io.BytesIO(pdf))
    page_text = [page.extract_text() or "" for page in reader.pages]

    assert len(page_text) > 1
    assert sum(text.count("Total Charge") for text in page_text) == 1
    assert "Total Charge" not in page_text[0]
    assert "Total Charge" in page_text[-1]


def test_safe_upload_base_strips_traversal_and_path_separators():
    assert safe_upload_base("../../evil/report.XML") == "report"
    assert safe_upload_base(r"..\\..\\evil\\report.XML") == "report"
    assert safe_upload_base("../=.XML") == "upload"


def test_unique_upload_base_prevents_duplicate_archive_paths():
    used = set()
    assert unique_upload_base("folder/plan.XML", used) == "plan"
    assert unique_upload_base(r"other\\plan.XML", used) == "plan_2"
    assert unique_upload_base("plan.XML", used) == "plan_3"


def test_upload_fingerprint_changes_for_revised_same_name_content():
    first = upload_fingerprint([("plan.XML", b"version one")])
    second = upload_fingerprint([("plan.XML", b"version two")])

    assert first != second


def test_csv_safe_cell_escapes_spreadsheet_formula_prefixes():
    for value in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)"):
        assert csv_safe_cell(value) == "'" + value
    assert csv_safe_cell("H1") == "H1"
    assert csv_safe_cell(12.5) == 12.5
