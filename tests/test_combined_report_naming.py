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


def test_cli_uses_custom_combined_name_for_output_and_zip(tmp_path):
    xml_files = []
    for ring in (1, 2):
        path = tmp_path / f"B18_S2_R{ring}.xml"
        path.write_text(MINIMAL_XML.format(plan_id=f"B18_S2_R{ring}"), encoding="utf-8")
        xml_files.append(path)
    output = tmp_path / "reports"

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "generate_batch_reports.py"),
            *(str(path) for path in xml_files),
            "--output",
            str(output),
            "--combined-name",
            "B18 S2 / Final:*?",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    expected_name = "B18_S2_Final.pdf"
    assert (output / expected_name).is_file()
    assert "combined_blast_reports.pdf" not in {path.name for path in output.iterdir()}
    with zipfile.ZipFile(output / "ringblast_reports_package.zip") as package:
        assert f"reports_pdf/{expected_name}" in package.namelist()
    assert expected_name in completed.stdout
