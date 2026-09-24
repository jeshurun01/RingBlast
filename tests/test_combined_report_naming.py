import json
import subprocess
import sys
import zipfile
from pathlib import Path

from app_utils import combined_report_filename


MINIMAL_XML = """<?xml version="1.0"?>
<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml">
  <IR:PlanId>{plan_id}</IR:PlanId>
  <IR:PlanName>{plan_id}</IR:PlanName>
  <DrillPlan>
    <Hole>
      <HoleId>1</HoleId><HoleName>H1</HoleName>
      <StartPoint><IR:PointX>0</IR:PointX><IR:PointY>0</IR:PointY><IR:PointZ>0</IR:PointZ></StartPoint>
      <EndPoint><IR:PointX>1</IR:PointX><IR:PointY>2</IR:PointY><IR:PointZ>8</IR:PointZ></EndPoint>
      <DrillBitDia>89</DrillBitDia>
    </Hole>
  </DrillPlan>
</DRPPlan>
"""


def test_combined_report_filename_keeps_backward_compatible_default():
    assert combined_report_filename(None) == "combined_blast_reports.pdf"
    assert combined_report_filename("  ") == "combined_blast_reports.pdf"


def test_combined_report_filename_normalizes_custom_name_and_extension():
    assert combined_report_filename("B18 S2 Production Report") == "B18_S2_Production_Report.pdf"
    assert combined_report_filename("B18 S2 Production Report.PDF") == "B18_S2_Production_Report.pdf"


def test_combined_report_filename_removes_paths_and_invalid_characters():
    assert combined_report_filename("../../B18:S2*Final?.pdf") == "B18_S2_Final.pdf"
    assert combined_report_filename("../?.pdf") == "combined_blast_reports.pdf"


def _write_batch(tmp_path, batch_label, rings=(1, 2)):
    xml_files = []
    for ring in rings:
        path = tmp_path / f"{batch_label}_R{ring}.xml"
        path.write_text(
            MINIMAL_XML.format(plan_id=f"{batch_label.replace(' ', '_')}_R{ring}"),
            encoding="utf-8",
        )
        xml_files.append(path)
    return xml_files


def _run_cli(xml_files, output, extra=()):
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "generate_batch_reports.py"),
            *(str(path) for path in xml_files),
            "--output",
            str(output),
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_cli_uses_custom_combined_name_for_output_and_zip(tmp_path):
    xml_files = _write_batch(tmp_path, "B18_S2")
    output = tmp_path / "reports"

    completed = _run_cli(xml_files, output, extra=("--combined-name", "B18 S2 / Final:*?"))

    expected_name = "B18_S2_Final.pdf"
    assert (output / expected_name).is_file()
    assert "combined_blast_reports.pdf" not in {path.name for path in output.iterdir()}
    # top view and package keep the stope label derived from the input XMLs
    assert (output / "B18_S2_Top_View_All_Rings.pdf").is_file()
    assert (output / "B18_S2_RingBlast_Report_Package.zip").is_file()
    with zipfile.ZipFile(output / "B18_S2_RingBlast_Report_Package.zip") as package:
        assert f"reports_pdf/{expected_name}" in package.namelist()
        assert "top_view/B18_S2_Top_View_All_Rings.pdf" in package.namelist()
        summary = json.loads(package.read("generation_summary.json"))
    assert summary["combined_pdf"] == expected_name
    assert expected_name in completed.stdout


def test_cli_default_names_use_stope_label_for_every_artifact(tmp_path):
    xml_files = _write_batch(tmp_path, "B27_S8", rings=(1, 10))
    output = tmp_path / "reports"

    completed = _run_cli(xml_files, output)

    for name in (
        "B27_S8_Combined_RingBlast_Report.pdf",
        "B27_S8_Top_View_All_Rings.pdf",
        "B27_S8_RingBlast_Report_Package.zip",
    ):
        assert (output / name).is_file(), name
        assert name in completed.stdout

    package_path = output / "B27_S8_RingBlast_Report_Package.zip"
    with zipfile.ZipFile(package_path) as package:
        assert package.testzip() is None
        entries = set(package.namelist())
        assert "reports_pdf/B27_S8_Combined_RingBlast_Report.pdf" in entries
        assert "top_view/B27_S8_Top_View_All_Rings.pdf" in entries
        assert "reports_pdf/B27_S8_R1_blast_report.pdf" in entries
        assert "reports_pdf/B27_S8_R10_blast_report.pdf" in entries
        assert "csv/B27_S8_R1_charge.csv" in entries
        assert "generation_summary.json" in entries
        assert not any("combined_blast_reports" in name for name in entries)
        assert not any(name.endswith("top_view_all_rings.pdf") for name in entries)
        summary = json.loads(package.read("generation_summary.json"))

    artifacts = summary["artifact_names"]
    assert summary["batch_label"] == "B27_S8"
    assert summary["source_files"] == ["B27_S8_R1.xml", "B27_S8_R10.xml"]
    assert summary["source_count"] == 2
    assert artifacts["batch_label"] == "B27_S8"
    assert artifacts["combined_pdf"] == "B27_S8_Combined_RingBlast_Report.pdf"
    assert artifacts["top_view_pdf"] == "B27_S8_Top_View_All_Rings.pdf"
    assert artifacts["package_zip"] == "B27_S8_RingBlast_Report_Package.zip"
    assert artifacts["zip_combined_entry"] == "reports_pdf/B27_S8_Combined_RingBlast_Report.pdf"
    assert artifacts["zip_top_view_entry"] == "top_view/B27_S8_Top_View_All_Rings.pdf"
    assert artifacts["per_ring_reports"] == [
        f"reports_pdf/B27_S8_R{ring}_blast_report.pdf" for ring in (1, 10)
    ]
    assert artifacts["per_ring_csvs"] == [
        f"csv/B27_S8_R{ring}_charge.csv" for ring in (1, 10)
    ]


def test_cli_derives_stope_label_from_spaced_source_file_names(tmp_path):
    """iRedes exports named "B27 S8_R1.XML" still yield B27_S8 artifacts."""
    xml_files = _write_batch(tmp_path, "B27 S8")
    output = tmp_path / "reports"

    _run_cli(xml_files, output)

    assert (output / "B27_S8_Combined_RingBlast_Report.pdf").is_file()
    assert (output / "B27_S8_Top_View_All_Rings.pdf").is_file()
    with zipfile.ZipFile(output / "B27_S8_RingBlast_Report_Package.zip") as package:
        entries = package.namelist()
        # individual ring entries keep identifying the ring
        assert sorted(name for name in entries if name.startswith("csv/")) == [
            "csv/B27 S8_R1_charge.csv", "csv/B27 S8_R2_charge.csv",
        ]
        assert sorted(name for name in entries if name.startswith("reports_pdf/")) == [
            "reports_pdf/B27 S8_R1_blast_report.pdf",
            "reports_pdf/B27 S8_R2_blast_report.pdf",
            "reports_pdf/B27_S8_Combined_RingBlast_Report.pdf",
        ]
