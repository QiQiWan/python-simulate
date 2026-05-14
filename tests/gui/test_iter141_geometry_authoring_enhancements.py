from __future__ import annotations

from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.app.viewport.tool_runtime import default_geometry_tool_runtime
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import (
    BooleanGeometryCommand,
    CopyGeometryCommand,
    CutVolumeCommand,
    ExtrudeSurfaceCommand,
    SetEntityCoordinatesCommand,
    TransformGeometryCommand,
)
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.desktop_interaction_recording import build_desktop_interaction_recording_contract


def _first_volume(project):
    return next(iter(project.geometry_model.volumes))


def _first_surface(project):
    return next(iter(project.geometry_model.surfaces))


def test_transform_copy_numeric_extrude_cut_boolean_commands():
    project = load_demo_project("foundation_pit_3d_beta")
    stack = CommandStack()
    volume_id = _first_volume(project)
    old_bounds = tuple(project.geometry_model.volumes[volume_id].bounds)

    result = stack.execute(TransformGeometryCommand(entity_ids=(volume_id,), entity_type="volume", translate=(1.0, 2.0, 3.0)), project)
    assert result.ok
    assert tuple(project.geometry_model.volumes[volume_id].bounds) != old_bounds
    stack.undo(project)
    assert tuple(project.geometry_model.volumes[volume_id].bounds) == old_bounds

    copy_result = stack.execute(CopyGeometryCommand(entity_ids=(volume_id,), entity_type="volume", offset=(2.0, 0.0, 0.0)), project)
    assert copy_result.ok
    assert copy_result.metadata["created_ids"]

    set_result = stack.execute(SetEntityCoordinatesCommand(entity_id=volume_id, entity_type="volume", x=5.0, y=6.0, z=-3.0, width=10.0, depth=8.0, height=6.0), project)
    assert set_result.ok
    assert project.geometry_model.volumes[volume_id].bounds == (0.0, 10.0, 2.0, 10.0, -6.0, 0.0)

    surface_id = _first_surface(project)
    extrude_result = stack.execute(ExtrudeSurfaceCommand(surface_id=surface_id, vector=(0.0, 0.0, -2.0)), project)
    assert extrude_result.ok
    extruded_id = extrude_result.affected_entities[-1]
    assert extruded_id in project.geometry_model.volumes

    cut_result = stack.execute(CutVolumeCommand(volume_id=extruded_id, axis="z", coordinate=-1.0), project)
    assert cut_result.ok
    assert len(cut_result.metadata["created_ids"]) == 2

    bool_result = stack.execute(BooleanGeometryCommand(operation="union", target_ids=tuple(cut_result.metadata["created_ids"])), project)
    assert bool_result.ok
    assert bool_result.metadata["parameters"]["operation"] == "union"


def test_selection_controller_multi_box_invert():
    project = load_demo_project("foundation_pit_3d_beta")
    state = ViewportState()
    state.update_from_geoproject_document(project)
    controller = SelectionController()
    volumes = list(project.geometry_model.volumes)
    selection = controller.select(volumes[0], "block", mode="replace")
    assert len(selection.items) == 1
    selection = controller.select(volumes[1], "block", mode="add")
    assert len(selection.items) == 2
    selection = controller.select(volumes[1], "block", mode="toggle")
    assert len(selection.items) == 1
    selection = controller.invert(state, kinds=("block",))
    assert len(selection.items) >= 1
    box = (-1e5, 1e5, -1e5, 1e5, -1e5, 1e5)
    selection = controller.box_select(state, box, kinds=("block",))
    assert len(selection.items) == len(project.geometry_model.volumes)


def test_runtime_edit_tools_drag_move_and_transform_tools():
    project = load_demo_project("foundation_pit_3d_beta")
    volume_id = _first_volume(project)
    old_bounds = tuple(project.geometry_model.volumes[volume_id].bounds)
    state = ViewportState(); state.update_from_geoproject_document(project)
    controller = SelectionController(); controller.select(volume_id, "block")
    runtime = default_geometry_tool_runtime(ToolContext(project, state, CommandStack(), metadata={"selection_controller": controller}))
    assert {"move", "copy", "rotate", "scale", "extrude", "cut", "boolean", "boolean_subtract"}.issubset(set(runtime.tools))
    runtime.activate("move")
    runtime.mouse_press(ToolEvent(world=(0.0, 0.0, 0.0), picked_entity_id=volume_id, metadata={"picked_kind": "block"}))
    output = runtime.mouse_release(ToolEvent(world=(1.0, 0.0, 0.0), picked_entity_id=volume_id, metadata={"picked_kind": "block"}))
    assert output.kind == "command"
    assert tuple(project.geometry_model.volumes[volume_id].bounds) != old_bounds


def test_phase_payload_exposes_iter141_geometry_authoring_contract():
    payload = build_phase_workbench_qt_payload("structures")
    interaction = payload["geometry_interaction"]
    assert interaction["edit_handles"] is True
    assert interaction["numeric_coordinate_input"] is True
    assert "ctrl_toggle" in interaction["multi_select"]
    assert "drag_handle" in interaction["transforms"]
    assert "extrude_surface" in interaction["solid_modeling"]
    assert interaction["semantic_property_panel"] is True
    recording = payload["desktop_interaction_recording"]
    assert recording["contract"] == "desktop_interaction_recording_contract_v1"
    assert len(recording["required_sequences"]) >= 6


def test_desktop_interaction_recording_contract_lists_required_sequences():
    contract = build_desktop_interaction_recording_contract().to_dict()
    names = {row["name"] for row in contract["required_sequences"]}
    assert {"edit_handles", "numeric_edit", "semantic_assignment", "complete_calculation"}.issubset(names)
