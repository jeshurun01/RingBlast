import pytest

from scripts.generate_batch_reports import custom_stemming_overrides, ring_label


def _hole(name, depth):
    return {
        "id": name,
        "name": name,
        "display": name,
        "x1": 0.0,
        "y1": 0.0,
        "z1": 0.0,
        "x2": 0.0,
        "y2": 0.0,
        "z2": depth,
    }


def test_ring_label_is_compact_for_source_names_without_underscores():
    assert ring_label("B1B Stope8R12") == "R12"


def test_rings_before_configured_start_keep_automatic_stemming():
    entry = {"base": "B1B_Stope8_R2", "holes": [_hole("H1", 10.0)]}

    assert custom_stemming_overrides(entry, start_ring=3) == {}


def test_custom_stemming_defaults_to_two_metres_and_alternates_only_deep_holes():
    entry = {
        "base": "B1B_Stope8_R3",
        "holes": [
            _hole("H1", 9.0),
            _hole("H2", 9.001),
            _hole("H3", 8.0),
            _hole("H4", 12.0),
            _hole("H5", 10.0),
        ],
    }

    assert custom_stemming_overrides(entry, start_ring=3) == {
        "H1": pytest.approx(2.0),
        "H2": pytest.approx(2.0),
        "H3": pytest.approx(2.0),
        "H4": pytest.approx(2.3),
        "H5": pytest.approx(2.0),
    }
