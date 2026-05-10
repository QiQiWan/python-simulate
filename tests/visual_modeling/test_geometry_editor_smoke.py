from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def test_geometry_editor_creates_point_line_surface_block():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    system.create_point(1.2, 0.0, -3.4)
    system.create_line((0.0, 0.0, 0.0), (4.0, 0.0, -4.0))
    system.create_surface([(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, -4.0), (0.0, 0.0, -4.0)])
    system.create_block((-2.0, -1.0, -0.5, 0.5, -2.0, -1.0), role="structure")

    payload = system.to_payload()
    kinds = {item["kind"] for item in payload["viewport"]["primitives"]}
    assert {"point", "edge", "surface", "block"}.issubset(kinds)
    assert payload["geometry_editor"]["counts"]["points"] >= 4
    assert payload["geometry_editor"]["counts"]["surfaces"] >= 1
    assert payload["geometry_editor"]["counts"]["blocks"] >= 25
