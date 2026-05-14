from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.tools.base import ToolContext, ToolEvent
from geoai_simkit.app.tools.geometry_creation_tools import LineTool
from geoai_simkit.app.viewport.snap_controller import SnapController
from geoai_simkit.app.viewport.viewport_state import ScenePrimitive, ViewportState
from geoai_simkit.commands import CommandStack
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.cad_structure_workflow import CAD_STRUCTURE_WORKFLOW_CONTRACT, build_cad_structure_workflow_payload


def _state() -> ViewportState:
    return ViewportState(primitives={
        "wall": ScenePrimitive(id="wall", kind="surface", entity_id="wall_001", bounds=(0.0, 0.0, 0.0, 0.0, -4.0, 0.0), style={"role": "wall"}, metadata={"semantic_type": "wall"}),
        "beam": ScenePrimitive(id="beam", kind="support", entity_id="beam_001", bounds=(0.0, 4.0, 0.0, 0.0, -1.0, -1.0), style={"role": "beam"}, metadata={"support_type": "beam", "points": [[0.0, 0.0, -1.0], [4.0, 0.0, -1.0]]}),
        "anchor": ScenePrimitive(id="anchor", kind="support", entity_id="anchor_001", bounds=(1.0, 4.0, 0.0, 0.0, -2.0, -3.0), style={"role": "anchor"}, metadata={"support_type": "anchor", "points": [[1.0, 0.0, -2.0], [4.0, 0.0, -3.0]]}),
        "stratum": ScenePrimitive(id="stratum", kind="partition_feature", entity_id="layer_001", bounds=(-5.0, 5.0, 0.0, 0.0, -2.0, -2.0), style={"role": "horizontal_layer"}, metadata={"type": "horizontal_layer", "points": [[-5.0, 0.0, -2.0], [5.0, 0.0, -2.0]]}),
        "excavation": ScenePrimitive(id="excavation", kind="partition_feature", entity_id="exc_001", bounds=(-2.0, 2.0, 0.0, 0.0, -3.0, 0.0), style={"role": "excavation_surface"}, metadata={"type": "excavation_surface", "points": [[-2.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 0.0, -3.0], [-2.0, 0.0, -3.0]]}),
    })


def test_iter156_contract_exposes_engineering_snap_and_constraints() -> None:
    assert __version__ in {"1.5.6-engineering-snap-constraints", "1.5.7-constraint-lock-toolbar", "1.5.8-constraint-visual-launcher-unification", "1.5.9-import-driven-assembly-unified-launch", "1.6.1-gui-action-audit-import-repair", "1.6.3-gui-action-dispatch-file-dialog-repair"}
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter156")
    payload = build_cad_structure_workflow_payload(project)
    assert payload["contract"] == CAD_STRUCTURE_WORKFLOW_CONTRACT
    assert CAD_STRUCTURE_WORKFLOW_CONTRACT in {"geoai_simkit_cad_structure_workflow_v5", "geoai_simkit_cad_structure_workflow_v6", "geoai_simkit_cad_structure_workflow_v7"}
    feedback = payload["structure_mouse_interaction"]["interaction_feedback"]
    assert "wall_endpoint" in feedback["snap_modes"]
    assert "beam_endpoint" in feedback["snap_modes"]
    assert "anchor_endpoint" in feedback["snap_modes"]
    assert "stratum_boundary_intersection" in feedback["snap_modes"]
    assert "excavation_contour_intersection" in feedback["snap_modes"]
    assert feedback["constraint_snap_modes"] == ["horizontal", "vertical", "along_edge", "along_normal"]


def test_semantic_snap_candidates_for_wall_beam_anchor_stratum_and_excavation() -> None:
    snap = SnapController(grid_enabled=False, endpoint_enabled=True, midpoint_enabled=True, tolerance=0.25)
    state = _state()
    assert snap.snap((0.03, 0.0, -0.02), state).mode == "wall_endpoint"
    assert snap.snap((4.03, 0.0, -1.02), state).mode == "beam_endpoint"
    assert snap.snap((1.03, 0.0, -2.02), state).mode == "anchor_endpoint"
    assert snap.snap((-4.95, 0.0, -2.02), state).mode == "stratum_boundary_intersection"
    assert snap.snap((-2.02, 0.0, -3.02), state).mode == "excavation_contour_intersection"


def test_constraint_projection_horizontal_vertical_edge_and_normal() -> None:
    snap = SnapController(grid_enabled=False, tolerance=0.5)
    state = _state()
    horizontal = snap.constrain((3.0, 0.2, -4.0), anchor=(1.0, 0.0, -1.0), modifiers=("shift",))
    assert horizontal.mode == "horizontal_constraint"
    assert horizontal.point == (3.0, 0.0, -1.0)
    vertical = snap.constrain((3.0, 0.2, -4.0), anchor=(1.0, 0.0, -1.0), modifiers=("ctrl",))
    assert vertical.mode == "vertical_constraint"
    assert vertical.point == (1.0, 0.0, -4.0)
    edge = snap.constrain((3.0, 0.0, -0.8), anchor=(0.0, 0.0, -1.0), state=state, requested="along_edge")
    assert edge.mode == "edge_aligned"
    assert edge.point == (3.0, 0.0, -1.0)
    normal = snap.constrain((3.0, 2.0, 5.0), anchor=(1.0, 0.0, -1.0), normal=(0.0, 0.0, 1.0), requested="along_normal")
    assert normal.mode == "normal_aligned"
    assert normal.point == (1.0, 0.0, 5.0)


def test_line_tool_preview_uses_shift_horizontal_constraint_metadata() -> None:
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="iter156_line")
    state = _state()
    context = ToolContext(document=project, viewport=state, command_stack=CommandStack(), metadata={"snap_controller": SnapController(grid_enabled=False)})
    tool = LineTool()
    tool.on_mouse_press(ToolEvent(world=(0.0, 0.0, -2.0), button="left"), context)
    preview = tool.on_mouse_move(ToolEvent(world=(5.0, 0.1, -4.0), modifiers=("shift",), metadata={}), context)
    assert preview.kind == "preview"
    assert preview.preview is not None
    assert preview.preview.points[-1] == (5.0, 0.0, -2.0)
    assert preview.preview.metadata["constraint_mode"] == "horizontal_constraint"
    assert preview.preview.metadata["constraint_label"] == "水平约束"
