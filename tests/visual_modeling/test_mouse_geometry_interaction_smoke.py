from geoai_simkit.app.geometry_mouse_interaction import GeometryMouseController
from geoai_simkit.app.visual_modeling_system import VisualModelingSystem


def test_mouse_geometry_interaction_contract():
    system = VisualModelingSystem.create_default({"dimension": "3d"})
    controller = GeometryMouseController(system)
    controller.set_mode("point")
    point_result = controller.click(1.0, -1.0)
    point_id = [eid for eid in point_result.entity_ids if eid in system.document.geometry.points][0]
    controller.set_mode("line")
    controller.click(0.0, 0.0)
    controller.click(2.0, -1.0)
    controller.click(4.0, -2.0)
    controller.set_mode("surface")
    controller.click(0.0, -3.0)
    controller.click(2.0, -3.0)
    controller.click(2.0, -5.0)
    assert controller.close_surface().ok
    controller.set_mode("block")
    controller.click(6.0, 0.0)
    block_result = controller.click(8.0, -2.0)
    block_id = [eid for eid in block_result.entity_ids if eid in system.document.geometry.blocks][0]
    controller.set_mode("move_point")
    assert controller.start_drag(point_id).ok
    assert controller.end_drag(2.0, -2.0).ok
    controller.set_mode("select")
    controller.click(0.0, 0.0, entity_id=point_id, entity_type="point")
    controller.click(0.0, 0.0, entity_id=block_id, entity_type="block", selection_modifier="add")
    assert len(system.document.selection.items) >= 2
    assert controller.box_select(-10, 2, 10, -8).ok
    action_ids = {row["id"] for row in controller.context_actions()}
    assert "delete_selected" in action_ids
