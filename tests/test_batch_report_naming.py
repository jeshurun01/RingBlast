"""Batch/stope label derivation and artifact naming for generate_batch_reports.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

from app_utils import DEFAULT_BATCH_LABEL, batch_stope_label, stope_label_from_name

SCRIPT = Path(__file__).parents[1] / "scripts" / "generate_batch_reports.py"


@pytest.fixture(scope="module")
def batch_script():
    """Import the CLI module (matplotlib Agg backend) for its pure helpers."""
    spec = importlib.util.spec_from_file_location("generate_batch_reports", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stope_label_strips_ring_suffix_and_keeps_case():
    assert stope_label_from_name("B27_S8_R1") == "B27_S8"
    assert stope_label_from_name("B27_S8_R10") == "B27_S8"
    assert stope_label_from_name("Kansoko_B1b_S8_R3") == "Kansoko_B1b_S8"


def test_stope_label_sanitizes_spaces_dashes_and_suffix_variants():
    assert stope_label_from_name("B27 S8_R1") == "B27_S8"
    assert stope_label_from_name("B27 S8 R10") == "B27_S8"
    assert stope_label_from_name("B27-S8-r2") == "B27-S8"
    assert stope_label_from_name("B27 S8_R1.XML") == "B27_S8"
    assert stope_label_from_name("/tmp/xmls/B27_S8_R1.xml") == "B27_S8"
    assert stope_label_from_name("B27 S8 S8bis_R1") == "B27_S8_S8bis"


def test_stope_label_keeps_names_without_ring_suffix():
    assert stope_label_from_name("B18_S2_Final") == "B18_S2_Final"
    assert stope_label_from_name("B22_PR02_S2") == "B22_PR02_S2"


def test_stope_label_empty_for_bare_ring_markers_and_blank_input():
    assert stope_label_from_name("R7") == ""
    assert stope_label_from_name("R7.XML") == ""
    assert stope_label_from_name("") == ""
    assert stope_label_from_name(None) == ""


def test_batch_stope_label_agrees_on_one_label_for_a_full_ring_batch():
    names = [f"B27_S8_R{ring}" for ring in range(1, 11)]
    assert batch_stope_label(names) == "B27_S8"
    assert batch_stope_label(["B27 S8_R1", "B27 S8_R2"]) == "B27_S8"


def test_batch_stope_label_uses_common_prefix_then_fallback():
    assert batch_stope_label(["B27_S8", "B27_S9"]) == "B27_S"
    assert batch_stope_label(["R1", "R2", "R3"]) == DEFAULT_BATCH_LABEL
    assert batch_stope_label([]) == DEFAULT_BATCH_LABEL
    assert batch_stope_label(["", " "]) == DEFAULT_BATCH_LABEL
    assert batch_stope_label([], fallback="Custom") == "Custom"


def test_batch_artifact_names_default_to_stope_prefixed_descriptive_names(batch_script):
    names = batch_script.batch_artifact_names("B27_S8")
    assert names == {
        "batch_label": "B27_S8",
        "combined_pdf": "B27_S8_Combined_RingBlast_Report.pdf",
        "top_view_pdf": "B27_S8_Top_View_All_Rings.pdf",
        "package_zip": "B27_S8_RingBlast_Report_Package.zip",
    }


def test_batch_artifact_names_honor_custom_combined_name_only(batch_script):
    names = batch_script.batch_artifact_names("B27_S8", combined_name="B27 S8 / Final:*?")
    assert names["combined_pdf"] == "B27_S8_Final.pdf"
    assert names["top_view_pdf"] == "B27_S8_Top_View_All_Rings.pdf"
    assert names["package_zip"] == "B27_S8_RingBlast_Report_Package.zip"


def test_batch_label_prefers_input_names_and_falls_back_to_plan_id(batch_script):
    entries = [
        {"base": "B27_S8_R1", "plan_id": "B27 S8_R1"},
        {"base": "B27_S8_R2", "plan_id": "B27 S8_R2"},
    ]
    assert batch_script.batch_label(entries) == "B27_S8"

    # a bare ring file name carries no stope: the XML plan id supplies it
    entries = [
        {"base": "R1", "plan_id": "Kansoko B5b S10_R1"},
        {"base": "R2", "plan_id": "Kansoko B5b S10_R2"},
    ]
    assert batch_script.batch_label(entries) == "Kansoko_B5b_S10"

    assert batch_script.batch_label([{"base": "R1", "plan_id": ""}]) == DEFAULT_BATCH_LABEL
