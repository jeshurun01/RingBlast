"""Zero/missing XML diameter uses 89 mm without changing source geometry."""
import io
import math

import pytest

from xml_to_image import build_charge_table, parse_xml


def xml_with_diameter(value):
    diameter = "" if value is None else f"<DrillBitDia>{value}</DrillBitDia>"
    return f'''<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml">
      <IR:PlanName>Diameter test</IR:PlanName><DrillPlan><Hole>
      <HoleId>1</HoleId><HoleName>H1</HoleName>
      <StartPoint><IR:PointX>2</IR:PointX><IR:PointY>3</IR:PointY><IR:PointZ>4</IR:PointZ></StartPoint>
      <EndPoint><IR:PointX>5</IR:PointX><IR:PointY>7</IR:PointY><IR:PointZ>16</IR:PointZ></EndPoint>
      {diameter}</Hole></DrillPlan></DRPPlan>'''.encode()


@pytest.mark.parametrize("value,source", [("0", "fallback_zero"), ("0.0", "fallback_zero"),
                                         (None, "fallback_missing"), ("", "fallback_missing"),
                                         ("  ", "fallback_missing")])
def test_zero_or_missing_diameter_retains_hole_and_applies_89_mm(value, source):
    data = xml_with_diameter(value)
    stream = io.BytesIO(data)
    _, _, holes, _ = parse_xml(stream, filename="diameter.XML", collar_correction="off")
    assert len(holes) == 1
    h = holes[0]
    assert h["diameter_mm"] == 89.0
    assert h["diameter_source"] == source
    assert tuple(h[k] for k in ("x1", "y1", "z1", "x2", "y2", "z2")) == (2, 3, 4, 5, 7, 16)
    row = build_charge_table(holes)[0]
    assert row["depth_m"] == 13.0
    assert row["stemming_m"] == 1.78
    assert row["charge_kg"] == round((13 - 1.78) * math.pi * (89 / 2000) ** 2 * 1150, 2)
    assert stream.getvalue() == data


@pytest.mark.parametrize("value", ["76", "89", "102.5", "127", "151"])
def test_positive_explicit_diameters_are_preserved(value):
    _, _, holes, _ = parse_xml(io.BytesIO(xml_with_diameter(value)))
    assert holes[0]["diameter_mm"] == float(value)
    assert holes[0]["diameter_source"] == "xml"


@pytest.mark.parametrize("value", ["-1", "-89", "NaN", "inf", "-inf", "1e999", "broken", "89mm"])
def test_invalid_diameter_is_rejected_not_defaulted(value):
    with pytest.raises(ValueError, match="diamètre"):
        parse_xml(io.BytesIO(xml_with_diameter(value)), filename="bad.XML")


def test_duplicate_hole_names_get_unique_id_based_keys_without_mutating_source_names():
    import xml.etree.ElementTree as ET
    from copy import deepcopy
    from xml_to_image import NS

    root = ET.fromstring(xml_with_diameter('0'))
    plan = root.find('drp:DrillPlan', NS)
    first = plan.find('drp:Hole', NS)
    first.find('drp:HoleName', NS).text = 'UnKnown'
    second = deepcopy(first)
    second.find('drp:HoleId', NS).text = '2'
    plan.append(second)
    _, _, holes, _ = parse_xml(io.BytesIO(ET.tostring(root)))
    assert [h['display'] for h in holes] == ['H1', 'H2']
    assert [h['name'] for h in holes] == ['UnKnown', 'UnKnown']
    assert all(h['label'].startswith(h['display'] + ' ') for h in holes)
    rows = build_charge_table(holes, stemming_overrides={'H1': 1, 'H2': 2})
    assert [r['stemming_m'] for r in rows] == [1, 2]
