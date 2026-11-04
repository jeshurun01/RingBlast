"""Batch ordering/identity, diagnostics and safe export regression tests."""
import io
import csv
import json
import zipfile

import matplotlib.pyplot as plt
import pytest
from pypdf import PdfReader

from app_utils import stope_label_from_name
from scripts.generate_batch_reports import (
    DEFAULT_CHARGE_PARAMS, DEFAULT_SETTINGS, build_report_pdf,
    build_top_view_grid, parse_batch, ring_key, ring_label,
)


@pytest.mark.parametrize("base,label", [("B16_S7_0_SLOT1", "SLOT1"),
                                       ("B16_S7_0_SLOT10", "SLOT10"),
                                       ("B27_S8_R10", "R10"), ("unknown", "unknown")])
def test_plan_labels_preserve_slot_and_ring_identity(base, label):
    assert ring_label(base) == label


def test_numeric_slot_order_and_batch_label():
    assert sorted(["B16_S7_0_SLOT10", "B16_S7_0_SLOT2", "B16_S7_0_SLOT1"], key=ring_key) == [
        "B16_S7_0_SLOT1", "B16_S7_0_SLOT2", "B16_S7_0_SLOT10"]
    assert stope_label_from_name("B16_S7_0_SLOT1.XML") == "B16_S7_0"


def test_parse_batch_rejects_duplicate_output_names_before_parsing(tmp_path):
    paths = []
    for folder in ("one", "two"):
        path = tmp_path / folder / "same.XML"
        path.parent.mkdir()
        path.write_text("not xml")
        paths.append(str(path))
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        parse_batch(paths)


def test_parse_batch_reports_failing_filename(tmp_path):
    path = tmp_path / "bad.XML"
    path.write_text("not xml")
    with pytest.raises(ValueError, match="bad.XML"):
        parse_batch([str(path)])


def test_cli_invalid_xml_fails_with_filename_without_creating_output(tmp_path, monkeypatch, capsys):
    from scripts import generate_batch_reports as batch
    path = tmp_path / 'bad.XML'
    path.write_text('not xml')
    out = tmp_path / 'out'
    monkeypatch.setattr('sys.argv', ['generate_batch_reports.py', str(path), '-o', str(out)])
    with pytest.raises(SystemExit) as exc:
        batch.main()
    assert exc.value.code == 2
    assert 'bad.XML' in capsys.readouterr().err
    assert not out.exists()


def test_parse_batch_rejects_backslashes_in_posix_basename(tmp_path, monkeypatch):
    # A backslash is a legal basename character on POSIX, but an actual path
    # separator on Windows. Exercise the unsafe-basename rule independently
    # of the runner OS without rejecting legitimate Windows directory paths.
    import posixpath
    from types import SimpleNamespace
    from scripts import generate_batch_reports as batch

    monkeypatch.setattr(batch, "os", SimpleNamespace(path=posixpath))
    with pytest.raises(ValueError, match='Unsafe'):
        parse_batch([str(tmp_path / r'folder\bad.XML')])


def hole():
    return {"id": "1", "name": "H1", "display": "H1", "label": "H1 10.000",
            "x1": 0, "y1": 0, "z1": 0, "x2": 0, "y2": 10, "z2": 0,
            "diameter_mm": 89, "diameter_source": "fallback_zero"}


def test_report_builder_honors_diameter_override():
    entry = {"plan_name": "Test", "plan_id": "Test", "holes": [hole()], "segments": []}
    pdf, rows, _ = build_report_pdf(entry, DEFAULT_SETTINGS,
                                   {**DEFAULT_CHARGE_PARAMS, "diameter_override_mm": 102})
    assert rows[0]["diameter_mm"] == 102
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_top_view_is_one_searchable_page_with_sorted_slot_labels_and_only_collars(tmp_path, monkeypatch):
    entries = [{"base": f"B16_S7_0_SLOT{i}", "holes": [hole()]} for i in (10, 2, 1)]
    path = tmp_path / "top.pdf"
    real_close = plt.close
    captured = {}

    def inspect_then_close(fig):
        if hasattr(fig, "axes") and len(fig.axes) == 2:
            ax = fig.axes[0]
            captured["labels"] = [t.get_text() for t in ax.texts]
            captured["lines"] = len(ax.lines)
            captured["points"] = sum(len(c.get_offsets()) for c in ax.collections)
        real_close(fig)

    monkeypatch.setattr(plt, "close", inspect_then_close)
    build_top_view_grid(entries, DEFAULT_SETTINGS, str(path))
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert all(label in text for label in ("SLOT1", "SLOT2", "SLOT10"))
    assert "R0" not in text
    assert "SLOT1 to SLOT10" in text
    assert captured["labels"][:3] == ["SLOT1", "SLOT2", "SLOT10"]
    assert captured["lines"] == 0
    assert captured["points"] == 3


def test_cli_exports_fallback_summary_safe_csv_and_intact_pdf_zip(tmp_path, monkeypatch, capsys):
    from scripts import generate_batch_reports as batch

    xml = '''<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml">
    <DrillPlan>{}</DrillPlan></DRPPlan>'''
    holes = []
    for name, diameter in [("=H1", "0"), ("H2", "102.5")]:
        holes.append(f'''<Hole><HoleId>{name}</HoleId><HoleName>{name}</HoleName>
        <StartPoint><IR:PointX>0</IR:PointX><IR:PointY>0</IR:PointY></StartPoint>
        <EndPoint><IR:PointX>0</IR:PointX><IR:PointY>10</IR:PointY></EndPoint>
        <DrillBitDia>{diameter}</DrillBitDia></Hole>''')
    path = tmp_path / "B16_S7_0_SLOT1.XML"
    path.write_text(xml.format("".join(holes)))
    out = tmp_path / "out"
    monkeypatch.setattr("sys.argv", ["generate_batch_reports.py", str(path), "-o", str(out)])
    batch.main()
    assert "89 mm for 1" in capsys.readouterr().out
    with zipfile.ZipFile(next(out.glob("*.zip"))) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        summary = json.loads(archive.read("generation_summary.json"))
        assert summary["diameter_fallback"]["holes"] == 1
        assert summary["rings"][0]["diameters_mm"] == [89, 102.5]
        rows = list(csv.DictReader(io.StringIO(archive.read("csv/B16_S7_0_SLOT1_charge.csv").decode())))
        assert [r["Diameter (mm)"] for r in rows] == ["89", "102.5"]
        assert rows[0]["Number"] == "'=H1"
        for name in archive.namelist():
            if name.endswith(".pdf"):
                assert len(PdfReader(io.BytesIO(archive.read(name))).pages) == 1
