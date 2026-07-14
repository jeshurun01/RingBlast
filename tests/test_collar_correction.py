import io
import math

from xml_to_image import parse_xml


def _xml(holes):
    hole_xml = "\n".join(
        f"""
        <Hole>
          <HoleId>{i}</HoleId>
          <HoleName>H{i}</HoleName>
          <StartPoint><IR:PointX>{sx}</IR:PointX><IR:PointY>{sy}</IR:PointY><IR:PointZ>0</IR:PointZ></StartPoint>
          <EndPoint><IR:PointX>{ex}</IR:PointX><IR:PointY>{ey}</IR:PointY><IR:PointZ>0</IR:PointZ></EndPoint>
          <DrillBitDia>89</DrillBitDia>
        </Hole>
        """
        for i, (sx, sy, ex, ey) in enumerate(holes, start=1)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DRPPlan xmlns:IR="http://www.iredes.org/xml" xmlns="http://www.iredes.org/xml/DrillRig">
  <IR:PlanName>Test plan</IR:PlanName>
  <IR:PlanId>TEST_PLAN</IR:PlanId>
  <Lines>
    <Line><IR:StartPoint><IR:PointX>-3</IR:PointX><IR:PointY>-2</IR:PointY></IR:StartPoint><IR:EndPoint><IR:PointX>-3</IR:PointX><IR:PointY>2</IR:PointY></IR:EndPoint></Line>
    <Line><IR:StartPoint><IR:PointX>3</IR:PointX><IR:PointY>-2</IR:PointY></IR:StartPoint><IR:EndPoint><IR:PointX>3</IR:PointX><IR:PointY>2</IR:PointY></IR:EndPoint></Line>
  </Lines>
  <Holes>{hole_xml}</Holes>
</DRPPlan>""".encode()


def test_auto_collar_correction_moves_convergent_gallery_center_starts_to_contour():
    xml_bytes = _xml([
        (0, 0, -10, 0),
        (0, 0, -8, 1),
        (0, 0, 9, 0),
        (0, 0, 7, -1),
    ])

    _, _, holes, _ = parse_xml(io.BytesIO(xml_bytes), filename="convergent.XML", collar_correction="auto")

    assert math.isclose(holes[0]["x1"], -3.0, abs_tol=1e-6)
    assert math.isclose(holes[0]["y1"], 0.0, abs_tol=1e-6)
    assert math.isclose(holes[2]["x1"], 3.0, abs_tol=1e-6)
    assert math.isclose(holes[2]["y1"], 0.0, abs_tol=1e-6)
    assert math.hypot(holes[0]["x2"] - holes[0]["x1"], holes[0]["y2"] - holes[0]["y1"]) == 7.0


def test_auto_collar_correction_does_not_move_starts_already_on_contour():
    xml_bytes = _xml([
        (-3, 0, -10, 0),
        (-3, 0.5, -8, 1),
        (3, 0, 9, 0),
        (3, -0.5, 7, -1),
    ])

    _, _, holes, _ = parse_xml(io.BytesIO(xml_bytes), filename="already_clean.XML", collar_correction="auto")

    assert [(h["x1"], h["y1"]) for h in holes] == [(-3.0, 0.0), (-3.0, 0.5), (3.0, 0.0), (3.0, -0.5)]


def test_collar_correction_can_be_disabled_for_original_coordinates():
    xml_bytes = _xml([(0, 0, -10, 0), (0, 0, 9, 0)])

    _, _, holes, _ = parse_xml(io.BytesIO(xml_bytes), filename="disabled.XML", collar_correction=False)

    assert [(h["x1"], h["y1"]) for h in holes] == [(0.0, 0.0), (0.0, 0.0)]


def test_collar_correction_is_opt_in_by_default():
    xml_bytes = _xml([(0, 0, -10, 0), (0, 0, 9, 0)])

    _, _, holes, _ = parse_xml(io.BytesIO(xml_bytes), filename="default.XML")

    assert [(h["x1"], h["y1"]) for h in holes] == [(0.0, 0.0), (0.0, 0.0)]
