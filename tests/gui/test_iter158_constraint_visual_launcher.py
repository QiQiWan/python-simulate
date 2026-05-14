from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import _launcher_info
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.tools.geometry_creation_tools import LineTool, PointTool
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


def test_iter158_contracts_expose_visual_lock_feedback() -> None:
    assert __version__ in {"1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter158")
    payload = build_cad_structure_workflow_payload(project)
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT == "geoai_simkit_cad_structure_workflow_v7"
    locking = payload["structure_mouse_interaction"]["interaction_feedback"]["constraint_locking"]
    assert locking["visual_feedback"] == ["locked_edge_highlight", "locked_normal_arrow", "continuous_placement_trail", "unlock_feedback"]


def test_snap_controller_records_trail_and_unlock_feedback() -> None:
    snap = SnapController(grid_enabled=False)
    state = _state()
    lock = snap.lock_constraint("along_edge", point=(3.0, 0.0, 4.0), state=state, target_entity_id="beam_001")
    assert lock.to_dict()["visualization"]["locked_edge_highlight"] is True
    snap.record_constraint_placement((1.0, 0.0, -1.0), kind="point", entity_id="p1")
    snap.record_constraint_placement((4.0, 0.0, -1.0), kind="point", entity_id="p2")
    data = snap.constraint_lock_dict()
    assert data["visualization"]["continuous_placement_trail"] is True
    assert len(data["trail"]) == 2
    assert data["metadata"]["placement_count"] == 2
    snap.unlock_constraint()
    feedback = snap.last_unlock_feedback_dict()
    assert feedback["unlocked"] is True
    assert feedback["previous_lock"]["mode"] == "edge_aligned"
    assert feedback["message"] == "约束锁定已解除"


def test_creation_commands_extend_constraint_trail_metadata() -> None:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter158_tools")
    state = _state()
    snap = SnapController(grid_enabled=False)
    snap.lock_constraint("along_edge", point=(0.0, 0.0, -1.0), state=state, target_entity_id="beam_001")
    context = ToolContext(document=project, viewport=state, command_stack=CommandStack(), metadata={"snap_controller": snap})

    ptool = PointTool()
    out = ptool.on_mouse_press(ToolEvent(world=(2.5, 3.0, 9.0), button="left", metadata={}), context)
    assert out.metadata["constraint_lock"]["trail"][-1] == [2.5, 0.0, -1.0]
    assert out.metadata["constraint_visualization"]["continuous_placement_trail"] is True

    ltool = LineTool()
    ltool.on_mouse_press(ToolEvent(world=(4.0, 1.0, 2.0), button="left", metadata={}), context)
    out2 = ltool.on_mouse_press(ToolEvent(world=(7.0, 2.0, 3.0), button="left", metadata={}), context)
    assert out2.metadata["constraint_lock"]["trail"][-1] == [7.0, 0.0, -1.0]
    assert len(out2.metadata["constraint_lock"]["trail"]) >= 3


def test_launcher_info_identifies_canonical_start_gui(tmp_path) -> None:
    info = _launcher_info(tmp_path, "start_gui.py")
    assert info["contract"] == "geoai_simkit_gui_launcher_info_v2"
    assert info["canonical_entrypoint"] == "start_gui.py"
    assert info["non_install_entrypoints"] == ["start_gui.py"]
    assert "run_gui.py" in info["removed_non_install_entrypoints"]
    assert info["version"] in {"1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
