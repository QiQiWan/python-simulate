from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.tools.geometry_creation_tools import LineTool, PointTool, SurfaceTool
from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.viewport_state import ScenePrimitive, ViewportState
from geoai_simkit.commands import CommandStack
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import CAD_STRUCTURE_WORKFLOW_CONTRACT, build_cad_structure_workflow_payload


def _state() -> ViewportState:
    return ViewportState(primitives={
        "beam": ScenePrimitive(
            id="beam",
            kind="support",
            entity_id="beam_001",
            bounds=(0.0, 10.0, 0.0, 0.0, -1.0, -1.0),
            style={"role": "beam"},
            metadata={"support_type": "beam", "points": [[0.0, 0.0, -1.0], [10.0, 0.0, -1.0]]},
        ),
        "wall": ScenePrimitive(
            id="wall",
            kind="surface",
            entity_id="wall_001",
            bounds=(2.0, 2.0, 0.0, 0.0, -5.0, 0.0),
            style={"role": "wall"},
            metadata={"semantic_type": "wall", "normal": [1.0, 0.0, 0.0]},
        ),
    })


def test_iter157_contract_exposes_constraint_lock_toolbar_and_context_menu() -> None:
    assert __version__ in {"1.5.7-constraint-lock-toolbar", "1.5.8-constraint-visual-launcher-unification", "1.5.9-import-driven-assembly-unified-launch", "1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter157")
    payload = build_cad_structure_workflow_payload(project)
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT
    assert CAD_STRUCTURE_WORKFLOW_CONTRACT in {"geoai_simkit_cad_structure_workflow_v6", "geoai_simkit_cad_structure_workflow_v7"}
    feedback = payload["structure_mouse_interaction"]["interaction_feedback"]
    locking = feedback["constraint_locking"]
    assert locking["explicit_toolbar"] == ["lock_along_edge", "lock_along_normal", "unlock"]
    assert locking["right_click_menu"] == ["lock_along_edge", "lock_along_normal", "unlock"]
    assert "surface" in locking["continuous_tools"]


def test_snap_controller_locks_along_edge_for_continuous_projection() -> None:
    snap = SnapController(grid_enabled=False, tolerance=0.2)
    state = _state()
    lock = snap.lock_constraint("along_edge", point=(5.0, 0.0, -0.5), state=state, target_entity_id="beam_001")
    assert lock.enabled
    assert lock.mode == "edge_aligned"
    assert lock.target_entity_id == "beam_001"
    first = snap.constrain((3.0, 0.8, -4.0), state=state)
    second = snap.constrain((8.0, -1.5, 2.0), state=state)
    assert first.mode == second.mode == "edge_aligned"
    assert first.point == (3.0, 0.0, -1.0)
    assert second.point == (8.0, 0.0, -1.0)
    assert first.to_dict()["metadata"]["locked"] is True
    assert snap.unlock_constraint().enabled is False


def test_snap_controller_locks_normal_for_repeated_points() -> None:
    snap = SnapController(grid_enabled=False)
    lock = snap.lock_constraint("along_normal", point=(2.0, 0.0, -3.0), normal=(1.0, 0.0, 0.0), target_entity_id="wall_001")
    assert lock.mode == "normal_aligned"
    result = snap.constrain((9.0, 4.0, 1.0))
    assert result.mode == "normal_aligned"
    assert result.point == (9.0, 0.0, -3.0)
    assert result.target_entity_id == "wall_001"


def test_creation_tools_use_locked_constraints_for_first_and_following_clicks() -> None:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter157_tools")
    state = _state()
    snap = SnapController(grid_enabled=False)
    snap.lock_constraint("along_edge", point=(0.0, 0.0, -1.0), state=state, target_entity_id="beam_001")
    context = ToolContext(document=project, viewport=state, command_stack=CommandStack(), metadata={"snap_controller": snap})

    point_tool = PointTool()
    preview = point_tool.on_mouse_move(ToolEvent(world=(4.0, 2.0, -5.0), metadata={}), context)
    assert preview.preview is not None
    assert preview.preview.points[-1] == (4.0, 0.0, -1.0)
    assert preview.preview.metadata["constraint_locked"] is True

    line_tool = LineTool()
    start_preview = line_tool.on_mouse_press(ToolEvent(world=(2.0, 5.0, 3.0), button="left", metadata={}), context)
    assert start_preview.preview is not None
    assert start_preview.preview.points[-1] == (2.0, 0.0, -1.0)
    move_preview = line_tool.on_mouse_move(ToolEvent(world=(6.0, -5.0, 9.0), metadata={}), context)
    assert move_preview.preview is not None
    assert move_preview.preview.points[-1] == (6.0, 0.0, -1.0)


def test_surface_tool_preview_reports_locked_constraint_metadata() -> None:
    state = _state()
    snap = SnapController(grid_enabled=False)
    snap.lock_constraint("along_normal", point=(2.0, 0.0, -3.0), normal=(1.0, 0.0, 0.0), target_entity_id="wall_001")
    context = ToolContext(document=GeoProjectDocument.create_foundation_pit({"dimension": "3d"}), viewport=state, command_stack=CommandStack(), metadata={"snap_controller": snap})
    tool = SurfaceTool()
    preview = tool.on_mouse_press(ToolEvent(world=(8.0, 2.0, 9.0), button="left", metadata={}), context)
    assert preview.preview is not None
    assert preview.preview.points[-1] == (8.0, 0.0, -3.0)
    assert preview.preview.metadata["constraint_mode"] == "normal_aligned"
    assert preview.preview.metadata["constraint_locked"] is True
