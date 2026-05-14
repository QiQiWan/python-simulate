from __future__ import annotations

from geoai_simkit.commands import CommandStack, CreateBlockCommand, CreateLineCommand, CreateSurfaceCommand
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import (
    CAD_STRUCTURE_WORKFLOW_CONTRACT,
    auto_assign_materials_by_recognized_strata_and_structures,
    build_cad_structure_workflow_payload,
    build_structure_mouse_interaction_payload,
    context_actions_for_selection,
    promote_geometry_to_structure,
    recommended_material_for_entity,
)


def _project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter153")
    project.populate_default_framework_content()
    return project


def test_structure_mouse_payload_explains_missing_interaction_contract() -> None:
    project = _project()
    payload = build_structure_mouse_interaction_payload(project)
    assert payload["contract"] == "geoai_simkit_structure_mouse_interaction_v1"
    assert {row["tool"] for row in payload["direct_creation_tools"]} >= {"point", "line", "surface", "block_box"}
    codes = {row["code"] for row in payload["why_visualization_was_not_enough"]}
    assert "display_actor_is_not_an_editor_object" in codes
    assert "material_assignment_not_layer_aware" in codes
    required = {row["element"] for row in payload["required_ui_elements"]}
    assert "direct_creation_buttons" in required
    assert "engineering_material_catalog" in required


def test_right_click_actions_promote_raw_geometry_to_engineering_objects() -> None:
    project = _project()
    stack = CommandStack()
    line_result = stack.execute(CreateLineCommand(start=(0, 0, 0), end=(4, 0, -2)), project)
    curve_id = line_result.affected_entities[0]
    surface_result = stack.execute(CreateSurfaceCommand(coords=((0, 0, 0), (4, 0, 0), (4, 0, -4), (0, 0, -4))), project)
    surface_id = surface_result.affected_entities[0]

    curve_actions = {row.action_id for row in context_actions_for_selection(project, curve_id, "curve")}
    surface_actions = {row.action_id for row in context_actions_for_selection(project, surface_id, "surface")}
    assert "promote_curve_beam" in curve_actions
    assert "promote_curve_anchor" in curve_actions
    assert "promote_surface_wall" in surface_actions
    assert "promote_surface_interface" in surface_actions

    beam = promote_geometry_to_structure(project, curve_id, "beam")
    wall = promote_geometry_to_structure(project, surface_id, "wall")
    assert beam["ok"] is True and beam["structure"]["geometry_ref"] == curve_id
    assert wall["ok"] is True and wall["structure"]["geometry_ref"] == surface_id
    assert beam["structure"]["material_id"] == "steel_q355"
    assert wall["structure"]["material_id"] == "concrete_c30"


def test_layer_aware_material_assignment_uses_borehole_depth_and_structure_type() -> None:
    project = _project()
    stack = CommandStack()
    top = stack.execute(CreateBlockCommand(bounds=(-5, 5, -1, 1, -2, -1), role="soil"), project).affected_entities[0]
    deep = stack.execute(CreateBlockCommand(bounds=(-5, 5, -1, 1, -26, -24), role="soil"), project).affected_entities[0]
    line = stack.execute(CreateLineCommand(start=(0, 0, 0), end=(1, 0, -1)), project).affected_entities[0]
    beam = promote_geometry_to_structure(project, line, "anchor")["structure"]["id"]

    # Clear materials so the batch assignment must make a recommendation.
    project.geometry_model.volumes[top].material_id = ""
    project.geometry_model.volumes[deep].material_id = ""
    project.structure_model.anchors[beam].material_id = ""

    result = auto_assign_materials_by_recognized_strata_and_structures(project)
    assert result["ok"] is True
    assert result["assigned_count"] >= 3
    assert project.geometry_model.volumes[top].material_id in project.material_library.soil_materials
    assert project.geometry_model.volumes[deep].material_id in project.material_library.soil_materials
    assert project.structure_model.anchors[beam].material_id == "steel_q355"

    rec = recommended_material_for_entity(project, top)
    assert rec["category"] == "soil"
    assert rec["material_id"] in project.material_library.soil_materials


def test_cad_structure_payload_exposes_structure_mouse_workflow() -> None:
    project = _project()
    payload = build_cad_structure_workflow_payload(project)
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT
    assert payload["structure_mouse_interaction"]["contract"] == "geoai_simkit_structure_mouse_interaction_v1"
    assert "auto_assign_recognized_strata_and_structures" in payload["quick_assignments"]
    actions = payload["actions_by_kind"]
    assert any(row["action_id"] == "promote_curve_beam" for row in actions["curve"])
    assert any(row["action_id"] == "promote_surface_wall" for row in actions["surface"])
