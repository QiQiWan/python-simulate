from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.core.gui_workflow_module_spec import GUI_WORKFLOW_MODULE_SPEC_CONTRACT, build_gui_workflow_module_payload
from geoai_simkit.services.cad_structure_workflow import (
    CAD_STRUCTURE_WORKFLOW_CONTRACT,
    apply_structure_context_action,
    auto_assign_materials_by_geometry_role,
    context_actions_for_selection,
    ensure_default_engineering_materials,
)
from geoai_simkit.services.demo_project_runner import load_demo_project


def test_iter151_payload_exposes_module_specs_and_material_library() -> None:
    assert __version__ == "1.5.4-viewport-workplane-hover-creation"
    payload = build_phase_workbench_qt_payload()
    specs = payload["workflow_module_specs"]
    assert specs["contract"] == GUI_WORKFLOW_MODULE_SPEC_CONTRACT
    module_keys = {row["key"] for row in specs["modules"]}
    assert {"structure_modeling", "material_library", "topology_preprocess", "meshing_workbench", "solver_setup_and_run", "benchmark_readiness"}.issubset(module_keys)
    assert payload["geometry_interaction"]["right_click_structure_actions"] is True
    assert payload["gui_cleanup"]["right_dock_tabs"] == ["属性", "语义/材料/阶段", "材料库"]
    assert "模块界面" in payload["gui_cleanup"]["bottom_tabs"]
    assert payload["cad_structure_workflow"]["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT


def test_iter151_gui_module_specs_define_required_controls() -> None:
    payload = build_gui_workflow_module_payload()
    assert payload["ok"] is True
    material = next(row for row in payload["modules"] if row["key"] == "material_library")
    element_keys = {row["key"] for row in material["required_elements"]}
    assert {"material_table", "assign_selected", "auto_assign_layers"}.issubset(element_keys)
    structure = next(row for row in payload["modules"] if row["key"] == "structure_modeling")
    actions = {action for element in structure["required_elements"] for action in element["actions"]}
    assert "promote_to_wall" in actions
    assert "assign_material" in actions


def test_iter151_context_menu_promotes_surface_line_volume_to_structures() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    ensure_default_engineering_materials(project)
    surface_id = next(iter(project.geometry_model.surfaces))
    curve_id = next(iter(project.geometry_model.curves))
    volume_id = next(iter(project.geometry_model.volumes))
    surface_actions = {row.action_id for row in context_actions_for_selection(project, surface_id)}
    curve_actions = {row.action_id for row in context_actions_for_selection(project, curve_id)}
    volume_actions = {row.action_id for row in context_actions_for_selection(project, volume_id)}
    assert "promote_surface_wall" in surface_actions
    assert "promote_curve_anchor" in curve_actions
    assert "promote_volume_soil" in volume_actions
    wall = apply_structure_context_action(project, surface_id, "promote_surface_wall", material_id="concrete_c30")
    anchor = apply_structure_context_action(project, curve_id, "promote_curve_anchor", material_id="steel_q355")
    soil = apply_structure_context_action(project, volume_id, "promote_volume_soil", material_id="soil_default")
    assert wall["ok"] is True and "structure" in wall
    assert anchor["ok"] is True and "structure" in anchor
    assert soil["ok"] is True and soil["volume"]["material_id"] == "soil_default"


def test_iter151_auto_material_assignment_covers_soil_and_structures() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    ensure_default_engineering_materials(project)
    volume_id = next(iter(project.geometry_model.volumes))
    project.geometry_model.volumes[volume_id].role = "soil"
    result = auto_assign_materials_by_geometry_role(project)
    assert result["ok"] is True
    assert project.geometry_model.volumes[volume_id].material_id
    assert "soil_default" in project.material_library.soil_materials
    assert "concrete_c30" in project.material_library.plate_materials
    assert "steel_q355" in project.material_library.beam_materials
