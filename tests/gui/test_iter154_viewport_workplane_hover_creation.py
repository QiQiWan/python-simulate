from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.tools.geometry_creation_tools import PointTool
from geoai_simkit.app.viewport.pyvista_adapter import PyVistaViewportAdapter
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.commands import CommandStack
from geoai_simkit.contracts.viewport import ViewportToolOutput
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import CAD_STRUCTURE_WORKFLOW_CONTRACT, build_cad_structure_workflow_payload


class _FakePlotter:
    def render(self) -> None:
        pass

    def remove_actor(self, _name: str) -> None:
        pass


def _project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter154")
    project.populate_default_framework_content()
    return project


def test_iter154_version_and_structure_workflow_v3_exposes_feedback_contract() -> None:
    assert __version__ in {"1.5.4-viewport-workplane-hover-creation", "1.5.5-snap-crosshair-surface-menu", "1.5.6-engineering-snap-constraints", "1.5.7-constraint-lock-toolbar", "1.5.8-constraint-visual-launcher-unification", "1.5.9-import-driven-assembly-unified-launch", "1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    payload = build_cad_structure_workflow_payload(_project())
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT
    assert payload["contract"] in {"geoai_simkit_cad_structure_workflow_v3", "geoai_simkit_cad_structure_workflow_v4", "geoai_simkit_cad_structure_workflow_v5", "geoai_simkit_cad_structure_workflow_v6", "geoai_simkit_cad_structure_workflow_v7"}
    feedback = payload["structure_mouse_interaction"]["interaction_feedback"]
    assert feedback["hover_highlight"] is True
    assert feedback["created_entity_auto_selection"] is True
    assert feedback["workplane_grid"] == ["XZ", "XY", "YZ"]
    point_tool = next(row for row in payload["structure_mouse_interaction"]["direct_creation_tools"] if row["tool"] == "point")
    assert point_tool["auto_select_after_create"] is True
    assert "移动预览" in point_tool["click_sequence"]


def test_point_tool_mouse_move_previews_and_create_command_requests_auto_selection() -> None:
    project = _project()
    context = ToolContext(document=project, viewport=None, command_stack=CommandStack())
    tool = PointTool()
    preview = tool.on_mouse_move(ToolEvent(x=10, y=20, world=(1.0, 0.0, -2.0)), context)
    assert preview.kind == "preview"
    assert preview.preview is not None
    assert preview.preview.kind == "point"
    assert preview.preview.points[0] == (1.0, 0.0, -2.0)

    created = tool.on_mouse_press(ToolEvent(x=10, y=20, world=(1.0, 0.0, -2.0), button="left"), context)
    assert created.kind == "command"
    assert created.metadata["auto_select_created"] is True
    assert created.metadata["select_kind"] == "point"
    assert created.metadata["select_entity_id"] in project.geometry_model.points


def test_pyvista_adapter_auto_selects_created_entity_through_selection_controller() -> None:
    controller = SelectionController()
    selection_seen = []
    adapter = PyVistaViewportAdapter(
        plotter=_FakePlotter(),
        selection_callback=lambda selection: selection_seen.append(selection),
    )
    adapter.runtime = type("Runtime", (), {"context": type("Context", (), {"metadata": {"selection_controller": controller}})()})()
    output = ViewportToolOutput(
        kind="command",
        tool="point",
        command_result={"affected_entities": ["point_001"]},
        metadata={"auto_select_created": True, "select_entity_id": "point_001", "select_kind": "point"},
    )
    adapter.apply_tool_output(output)
    assert controller.selected_ids() == ["point_001"]
    assert selection_seen
    assert selection_seen[-1].items[0].entity_id == "point_001"
