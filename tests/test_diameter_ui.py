"""Exercise the real Streamlit app's default tables and PDF/CSV generation."""
import csv
import io
from pathlib import Path

from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from xml_to_image import build_charge_table, parse_xml


def test_ui_warns_on_fallback_preserves_decimal_diameter_and_generates():
    xml = '''<DRPPlan xmlns="http://www.iredes.org/xml/DrillRig" xmlns:IR="http://www.iredes.org/xml">
    <IR:PlanName>UI diameter test</IR:PlanName><DrillPlan>{}</DrillPlan></DRPPlan>'''
    holes = []
    for index, diameter in enumerate((0, 102.5), start=1):
        holes.append(f'''<Hole><HoleId>{index}</HoleId><HoleName>UnKnown</HoleName>
        <StartPoint><IR:PointX>0</IR:PointX><IR:PointY>0</IR:PointY></StartPoint>
        <EndPoint><IR:PointX>0</IR:PointX><IR:PointY>10</IR:PointY></EndPoint>
        <DrillBitDia>{diameter}</DrillBitDia></Hole>''')
    plan_name, plan_id, parsed_holes, segments = parse_xml(io.BytesIO(xml.format("".join(holes)).encode()))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30)
    # AppTest cannot drive file_uploader. Seed its already-parsed state, then exercise
    # the actual UI, editor defaults and Generate button (parser tested separately).
    app.session_state["uploaded_parse_config"] = {"files": (), "auto_correct_gallery_collars": False}
    app.session_state["parsed_data"] = {"SLOT1": {"plan_name": plan_name, "plan_id": plan_id,
                                                  "holes": parsed_holes, "segments": segments}}
    app.run()
    assert not app.exception
    assert any("89 mm fallback applied to 1 holes" in w.value for w in app.warning)
    assert list(app.session_state["df_SLOT1"]["Diameter (mm)"]) == [89, 102.5]
    assert list(app.session_state["df_SLOT1"]["Hole"]) == ['H1', 'H2']
    next(b for b in app.button if "Generate blast report" in b.label).click().run()
    assert not app.exception
    result = app.session_state["results"]["SLOT1"]
    rows = list(csv.DictReader(io.StringIO(result["csv"].decode())))
    assert [float(r["Diameter (mm)"]) for r in rows] == [89, 102.5]
    assert [float(r['Charge (kg)']) for r in rows] == [r['charge_kg'] for r in build_charge_table(parsed_holes)]
    assert len(PdfReader(io.BytesIO(result["pdf"])).pages) == 1
