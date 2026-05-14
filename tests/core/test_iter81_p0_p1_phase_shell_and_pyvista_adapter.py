from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.viewport.headless_viewport import HeadlessViewport
from geoai_simkit.app.viewport.pyvista_adapter import PyVistaViewportAdapter
from geoai_simkit.app.viewport.tool_runtime import default_geometry_tool_runtime
from geoai_simkit.app.viewport.workplane import WorkPlaneController, project_point_to_plane, ray_plane_intersection
from geoai_simkit.commands import CommandStack
from geoai_simkit.geoproject.document import GeoProjectDocument
from geoai_simkit.services.workbench_phase_service import phase_workbench_ui_state


class _FakePlotter:
    def __init__(self):
        self.iren = None
        self.picker = None
        self.rendered = False

    def render(self):
        self.rendered = True


def test_p0_phase_ui_state_maps_phase_tools_to_runtime_tools():
    geology = phase_workbench_ui_state("geology", "create_geology_point")
    assert geology["contract"] == "phase_workbench_ui_state_v1"
    assert geology["active_phase"] == "geology"
    assert geology["runtime_tool"] == "point"
    assert [tab["key"] for tab in geology["phase_tabs"]] == ["geology", "structures", "mesh", "staging", "solve", "results"]
    assert "create" in geology["toolbar_groups"]

    structures = phase_workbench_ui_state("structures", "surface")
    assert structures["runtime_tool"] == "surface"
    assert any(panel["key"] == "structure_properties" for panel in structures["right_panels"])

    mesh = phase_workbench_ui_state("mesh", "generate_tet4")
    assert mesh["runtime_tool"] == "select"
    assert mesh["selection_filter"] != geology["selection_filter"]


def test_p1_workplane_projection_and_ray_intersection_are_headless_safe():
    controller = WorkPlaneController()
    controller.set_named_plane("xz", offset=2.0)
    assert project_point_to_plane((1.0, 9.0, 3.0), controller.active) == (1.0, 2.0, 3.0)
    hit = ray_plane_intersection((0.0, 10.0, 0.0), (0.0, -1.0, 0.0), controller.active)
    assert hit == (0.0, 2.0, 0.0)
    assert controller.to_dict()["metadata"]["contract"] == "work_plane_controller_v1"


def test_p1_pyvista_adapter_builds_tool_events_without_pyvista_dependency():
    adapter = PyVistaViewportAdapter(_FakePlotter())
    adapter.workplane.set_named_plane("xz", offset=0.0)
    event = adapter.build_tool_event(button="left", x=4.0, y=6.0)
    assert event.button == "left"
    assert event.world == (4.0, 0.0, 6.0)
    assert event.metadata["workplane"] == "xz"


def test_p1_phase_tool_payload_can_drive_runtime_creation():
    project = GeoProjectDocument.create_empty(name="phase-tool-runtime")
    viewport = HeadlessViewport()
    viewport.load_document(project)
    runtime = default_geometry_tool_runtime(ToolContext(document=project, viewport=viewport, command_stack=CommandStack()))

    payload = {"key": "create_geology_point", "metadata": {"runtime_tool": "point"}}
    out = runtime.activate_phase_tool(payload)
    assert out.kind == "message"
    assert runtime.active_tool_key == "point"
    result = runtime.mouse_press(ToolEvent(world=(2.0, 0.0, 3.0), button="left"))
    assert result.kind == "command"
    assert len(project.geometry_model.points) == 1
