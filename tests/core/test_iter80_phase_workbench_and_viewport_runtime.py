from geoai_simkit.app.controllers.workbench_phase_actions import WorkbenchPhaseActionController
from geoai_simkit.app.viewport import default_geometry_tool_runtime
from geoai_simkit.app.viewport.headless_viewport import HeadlessViewport
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.commands import CommandStack
from geoai_simkit.geoproject.document import GeoProjectDocument
from geoai_simkit.services.workbench_phase_service import build_workbench_phase_state, build_workbench_phases


def test_six_workbench_phases_have_phase_specific_toolbars():
    phases = build_workbench_phases()
    assert [phase.key for phase in phases] == ["geology", "structures", "mesh", "staging", "solve", "results"]
    mesh = build_workbench_phase_state("mesh")
    assert mesh.active_phase == "mesh"
    assert any(tool.key == "local_remesh" for tool in mesh.active_phase_spec().toolbar.tools)
    geology = build_workbench_phase_state("geology")
    assert any(tool.key == "optimize_stl" for tool in geology.active_phase_spec().toolbar.tools)
    assert mesh.selection_filter != geology.selection_filter


def test_workbench_phase_controller_is_serializable():
    payload = WorkbenchPhaseActionController().state("staging")
    assert payload["active_phase"] == "staging"
    assert payload["active_toolbar"]["phase_key"] == "staging"
    assert len(payload["phases"]) == 6


def test_viewport_tool_runtime_creates_point_line_surface_and_box():
    project = GeoProjectDocument.create_empty(name="tool-runtime")
    viewport = HeadlessViewport()
    viewport.load_document(project)
    runtime = default_geometry_tool_runtime(ToolContext(document=project, viewport=viewport, command_stack=CommandStack()))

    runtime.activate("point")
    point_out = runtime.mouse_press(ToolEvent(world=(1.0, 2.0, 3.0), button="left"))
    assert point_out.kind == "command"
    assert project.geometry_model.points

    runtime.activate("line")
    preview = runtime.mouse_press(ToolEvent(world=(0.0, 0.0, 0.0), button="left"))
    assert preview.kind == "preview"
    move = runtime.mouse_move(ToolEvent(world=(1.0, 0.0, 0.0)))
    assert move.preview is not None
    line_out = runtime.mouse_press(ToolEvent(world=(1.0, 0.0, 0.0), button="left"))
    assert line_out.kind == "command"
    assert project.geometry_model.curves

    runtime.activate("surface")
    runtime.mouse_press(ToolEvent(world=(0.0, 0.0, 0.0), button="left"))
    runtime.mouse_press(ToolEvent(world=(1.0, 0.0, 0.0), button="left"))
    runtime.mouse_press(ToolEvent(world=(1.0, 0.0, 1.0), button="left"))
    surface_out = runtime.key_press("Enter")
    assert surface_out.kind == "command"
    assert project.geometry_model.surfaces

    runtime.activate("block_box")
    runtime.mouse_press(ToolEvent(world=(0.0, 0.0, 0.0), button="left"))
    box_preview = runtime.mouse_move(ToolEvent(world=(1.0, 1.0, 1.0)))
    assert box_preview.kind == "preview"
    box_out = runtime.mouse_press(ToolEvent(world=(1.0, 1.0, 1.0), button="left"))
    assert box_out.kind == "command"
    assert project.geometry_model.volumes

    snap = runtime.snapshot()
    assert "point" in snap["registered_tools"]
    assert snap["metadata"]["contract"] == "viewport_tool_runtime_v2"
