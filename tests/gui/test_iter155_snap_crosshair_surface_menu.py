from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.tools.geometry_creation_tools import PointTool, SurfaceTool
from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.viewport_state import ScenePrimitive, ViewportState
from geoai_simkit.commands import CommandStack
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import CAD_STRUCTURE_WORKFLOW_CONTRACT, build_cad_structure_workflow_payload


def _project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter155")
    project.populate_default_framework_content()
    return project


def test_iter155_contract_exposes_crosshair_snap_hints_and_surface_menu() -> None:
    assert __version__ in {"1.5.5-snap-crosshair-surface-menu", "1.5.6-engineering-snap-constraints", "1.5.7-constraint-lock-toolbar", "1.5.8-constraint-visual-launcher-unification", "1.5.9-import-driven-assembly-unified-launch", "1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    payload = build_cad_structure_workflow_payload(_project())
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT
    assert payload["contract"] in {"geoai_simkit_cad_structure_workflow_v4", "geoai_simkit_cad_structure_workflow_v5", "geoai_simkit_cad_structure_workflow_v6", "geoai_simkit_cad_structure_workflow_v7"}
    feedback = payload["structure_mouse_interaction"]["interaction_feedback"]
    assert feedback["screen_space_crosshair"] is True
    assert feedback["grid_snap_visible_point"] is True
    assert feedback["endpoint_midpoint_snap_hints"] is True
    assert feedback["surface_right_click_completion_menu"] == ["finish", "undo_last_point", "cancel"]


def test_point_tool_preview_carries_crosshair_and_snap_metadata() -> None:
    context = ToolContext(document=_project(), viewport=None, command_stack=CommandStack())
    event = ToolEvent(
        x=5,
        y=8,
        world=(1.1, 0.0, 2.1),
        metadata={"snap": {"point": [1.0, 0.0, 2.0], "snapped": True, "mode": "grid", "distance": 0.14}},
    )
    output = PointTool().on_mouse_move(event, context)
    assert output.kind == "preview"
    assert output.preview is not None
    meta = output.preview.metadata
    assert meta["screen_space_crosshair"] is True
    assert meta["snap_mode"] == "grid"
    assert meta["snap_label"] == "网格"
    assert meta["snapped"] is True


def test_surface_tool_right_click_workflow_metadata_and_commit() -> None:
    project = _project()
    context = ToolContext(document=project, viewport=None, command_stack=CommandStack())
    tool = SurfaceTool()
    for pt in [(0, 0, 0), (1, 0, 0), (1, 0, 1)]:
        out = tool.on_mouse_press(ToolEvent(world=pt, button="left", metadata={"snap": {"point": list(pt), "mode": "endpoint", "snapped": True}}), context)
    assert out.preview is not None
    assert out.preview.metadata["right_click_completion_menu"] is True
    assert out.preview.metadata["can_finish"] is True
    committed = tool.on_mouse_press(ToolEvent(button="right"), context)
    assert committed.kind == "command"
    assert committed.metadata["auto_select_created"] is True


def test_snap_controller_provides_endpoint_and_midpoint_candidates_from_bounds() -> None:
    state = ViewportState(primitives={
        "line_1": ScenePrimitive(id="line_1", entity_id="curve_1", kind="curve", bounds=(0.0, 2.0, 0.0, 0.0, 0.0, 0.0), metadata={}),
    })
    snap = SnapController(enabled=True, grid_enabled=False, endpoint_enabled=True, midpoint_enabled=True, tolerance=0.2)
    endpoint = snap.snap((0.05, 0.0, 0.0), state)
    assert endpoint.snapped is True
    assert endpoint.mode == "endpoint"
    middle = snap.snap((1.05, 0.0, 0.0), state)
    assert middle.snapped is True
    assert middle.mode == "midpoint"
