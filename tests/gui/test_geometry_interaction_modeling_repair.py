from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.tool_runtime import default_geometry_tool_runtime
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def test_snap_controller_snaps_to_block_endpoint_and_grid() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    state = ViewportState()
    state.update_from_geoproject_document(project)
    snap = SnapController(spacing=1.0, tolerance=0.8)
    result = snap.snap((0.21, 0.19, -0.12), state)
    assert result.snapped
    assert result.mode in {"endpoint", "midpoint", "grid"}
    grid = SnapController(endpoint_enabled=False, midpoint_enabled=False, spacing=1.0)
    grid_result = grid.snap((0.49, 0.51, -0.49), state)
    assert grid_result.mode == "grid"
    assert grid_result.point == (0.0, 1.0, 0.0)


def test_runtime_creates_geometry_and_supports_surface_backspace() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    state = ViewportState()
    stack = CommandStack()
    runtime = default_geometry_tool_runtime(ToolContext(document=project, viewport=state, command_stack=stack))

    before_points = len(project.geometry_model.points)
    runtime.activate("point")
    output = runtime.mouse_press(ToolEvent(world=(1.0, 2.0, 3.0), button="left"))
    assert output.kind == "command"
    assert len(project.geometry_model.points) == before_points + 1

    runtime.activate("surface")
    runtime.mouse_press(ToolEvent(world=(0.0, 0.0, 0.0), button="left"))
    runtime.mouse_press(ToolEvent(world=(1.0, 0.0, 0.0), button="left"))
    runtime.mouse_press(ToolEvent(world=(1.0, 1.0, 0.0), button="left"))
    back = runtime.key_press("Backspace")
    assert back.kind == "preview"
    runtime.mouse_press(ToolEvent(world=(0.0, 1.0, 0.0), button="left"))
    commit = runtime.key_press("Enter")
    assert commit.kind == "command"
    assert project.geometry_model.surfaces


def test_phase_workbench_payload_exposes_interactive_geometry_contract() -> None:
    payload = build_phase_workbench_qt_payload("structures")
    interaction = payload["geometry_interaction"]
    assert interaction["mouse_creation"] is True
    assert "endpoint" in interaction["snap_modes"]
    assert "XZ" in interaction["workplanes"]
    assert interaction["undo_redo"] is True


def test_phase_workbench_qt_source_binds_runtime_to_pyvista_adapter() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "default_geometry_tool_runtime" in source
    assert "self.viewport_adapter.bind_runtime" in source
    assert "self.viewport_adapter.bind_events()" in source
    assert "self.viewport_adapter.bind_viewport_state" in source
    assert "CommandStack()" in source
    assert "_set_workplane" in source
    assert "_toggle_snap" in source


def test_pyvista_adapter_has_real_picker_and_selection_overlay_contract() -> None:
    source = Path("src/geoai_simkit/app/viewport/pyvista_adapter.py").read_text(encoding="utf-8")
    assert "vtkPropPicker" in source
    assert "SnapController" in source
    assert "render_selection" in source
    assert "RightButtonPressEvent" in source
    assert "bind_viewport_state" in source
