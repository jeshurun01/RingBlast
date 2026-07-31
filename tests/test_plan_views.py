import io
import math

import matplotlib.pyplot as plt
import pytest

from xml_to_image import build_figure, hole_length, parse_xml, project_plan


XML_3D = b'''<?xml version="1.0"?>
<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml">
  <IR:PlanId>VIEW_TEST</IR:PlanId>
  <IR:PlanName>View test</IR:PlanName>
  <DrillPlan>
    <Hole>
      <HoleId>1</HoleId><HoleName>H1</HoleName>
      <StartPoint><IR:PointX>2</IR:PointX><IR:PointY>3</IR:PointY><IR:PointZ>4</IR:PointZ></StartPoint>
      <EndPoint><IR:PointX>5</IR:PointX><IR:PointY>7</IR:PointY><IR:PointZ>16</IR:PointZ></EndPoint>
      <DrillBitDia>89</DrillBitDia>
    </Hole>
  </DrillPlan>
  <Lines>
    <Line>
      <IR:StartPoint><IR:PointX>1</IR:PointX><IR:PointY>2</IR:PointY></IR:StartPoint>
      <IR:EndPoint><IR:PointX>6</IR:PointX><IR:PointY>8</IR:PointY></IR:EndPoint>
    </Line>
  </Lines>
</DRPPlan>'''


SETTINGS = {
    "color_hole": "#000000",
    "color_outline": "#000000",
    "color_dot": "#000000",
    "color_background": "#ffffff",
    "show_grid": True,
    "scale_bar_length": 1.0,
    "fig_width": 5,
    "fig_height": 4,
}


def test_parse_xml_preserves_3d_coordinates_and_real_hole_length():
    _, _, holes, _ = parse_xml(io.BytesIO(XML_3D), filename="view.xml")

    assert (holes[0]["z1"], holes[0]["z2"]) == (4.0, 16.0)
    assert hole_length(holes[0]) == 13.0
    assert holes[0]["label"] == "H1 13.000"


def test_top_and_bottom_views_are_coherent_mirrored_xy_projections():
    _, _, holes, segments = parse_xml(io.BytesIO(XML_3D), filename="view.xml")

    top_holes, top_segments = project_plan(holes, segments, "top")
    bottom_holes, bottom_segments = project_plan(holes, segments, "bottom")

    assert (top_holes[0]["x1"], top_holes[0]["y1"], top_holes[0]["x2"], top_holes[0]["y2"]) == (2.0, 3.0, 5.0, 7.0)
    assert (bottom_holes[0]["x1"], bottom_holes[0]["y1"], bottom_holes[0]["x2"], bottom_holes[0]["y2"]) == (-2.0, 3.0, -5.0, 7.0)
    assert top_segments == [(1.0, 2.0, 6.0, 8.0)]
    assert bottom_segments == [(-1.0, 2.0, -6.0, 8.0)]
    assert holes[0]["x1"] == 2.0  # input data is not mutated


def test_build_figure_applies_selected_bottom_view():
    plan_name, plan_id, holes, segments = parse_xml(io.BytesIO(XML_3D), filename="view.xml")
    settings = {**SETTINGS, "view_orientation": "bottom"}

    fig, _ = build_figure(plan_name, plan_id, holes, segments, settings)
    hole_line = fig.axes[0].lines[1]

    assert list(hole_line.get_xdata()) == [-2.0, -5.0]
    assert "vue de dessous" in fig.axes[0].get_title().lower()
    plt.close(fig)


def test_parse_xml_rejects_valid_xml_without_renderable_holes():
    empty = b'''<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml"><IR:PlanName>Empty</IR:PlanName></DRPPlan>'''

    with pytest.raises(ValueError, match="aucun trou exploitable"):
        parse_xml(io.BytesIO(empty), filename="empty.xml")


@pytest.mark.parametrize(
    ("xml_bytes", "message"),
    [
        (XML_3D.replace(b"<IR:PointX>2</IR:PointX>", b"<IR:PointX>NaN</IR:PointX>"), "finies"),
        (XML_3D.replace(b"<IR:PointY>3</IR:PointY>", b"<IR:PointY>inf</IR:PointY>"), "finies"),
        (XML_3D.replace(b"<DrillBitDia>89</DrillBitDia>", b"<DrillBitDia>-89</DrillBitDia>"), "diamètre"),
        (XML_3D.replace(b"<DrillBitDia>89</DrillBitDia>", b"<DrillBitDia>NaN</DrillBitDia>"), "diamètre"),
    ],
)
def test_parse_xml_rejects_non_finite_coordinates_and_invalid_diameters(xml_bytes, message):
    with pytest.raises(ValueError, match=message):
        parse_xml(io.BytesIO(xml_bytes), filename="invalid.xml")
