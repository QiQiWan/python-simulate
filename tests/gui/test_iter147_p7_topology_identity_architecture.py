from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.app.viewport.pick_adapter import pick_by_entity_id, pick_from_tool_event
from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.topology_identity_commands import BuildTopologyIdentityIndexCommand
from geoai_simkit.geoproject.cad_shape_store import CadOperationHistoryRecord, CadShapeRecord, CadTopologyLineageRecord, CadTopologyRecord
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.topology_identity_service import build_topology_identity_index, resolve_topology_selection, validate_topology_identity_index
from geoai_simkit.services.topology_material_phase_binding import bind_topology_material_phase


def _attach_demo_shape(project):
    volume_id = next(iter(project.geometry_model.volumes))
    bounds = project.geometry_model.volumes[volume_id].bounds
    shape_id = "shape:p7:volume"
    solid_id = "solid:p7:volume"
    face_id = "face:p7:xmin"
    edge_id = "edge:p7:bottom_x"
    project.cad_shape_store.shapes[shape_id] = CadShapeRecord(
        id=shape_id,
        name="P7 Shape",
        kind="solid",
        source_entity_ids=[volume_id],
        backend="cad_facade",
        native_shape_available=True,
        topology_ids=[solid_id, face_id, edge_id],
        material_id="soil_upper",
        phase_ids=["initial"],
        metadata={"native_brep_certified": True},
    )
    project.cad_shape_store.topology_records[solid_id] = CadTopologyRecord(id=solid_id, shape_id=shape_id, kind="solid", source_entity_id=volume_id, bounds=bounds, persistent_name="p7/solid/0", native_tag="solid-native")
    project.cad_shape_store.topology_records[face_id] = CadTopologyRecord(
        id=face_id,
        shape_id=shape_id,
        kind="face",
        source_entity_id=volume_id,
        parent_id=solid_id,
        bounds=(bounds[0], bounds[0], bounds[2], bounds[3], bounds[4], bounds[5]),
        persistent_name="p7/face/xmin",
        native_tag="face-native-xmin",
        orientation="xmin",
        metadata={"native_topology": True},
    )
    project.cad_shape_store.topology_records[edge_id] = CadTopologyRecord(
        id=edge_id,
        shape_id=shape_id,
        kind="edge",
        source_entity_id=volume_id,
        parent_id=face_id,
        bounds=(bounds[0], bounds[1], bounds[2], bounds[2], bounds[4], bounds[4]),
        persistent_name="p7/edge/bottom_x",
        native_tag="edge-native-bottom-x",
        orientation="bottom_x",
        metadata={"native_topology": True},
    )
    project.cad_shape_store.operation_history["op:p7"] = CadOperationHistoryRecord(
        id="op:p7",
        operation="boolean_cut",
        input_shape_ids=[shape_id],
        output_shape_ids=[shape_id],
        native_backend_used=True,
        fallback_used=False,
    )
    project.cad_shape_store.topology_lineage["lineage:p7:face"] = CadTopologyLineageRecord(
        id="lineage:p7:face",
        operation_id="op:p7",
        input_topology_ids=[face_id],
        output_topology_ids=[face_id],
        lineage_type="preserved",
        topology_kind="face",
        confidence="native",
        native_backend_used=True,
    )
    return volume_id, shape_id, solid_id, face_id, edge_id


def test_p7_topology_identity_index_unifies_entities_shapes_topology_and_lineage():
    project = load_demo_project("foundation_pit_3d_beta")
    volume_id, shape_id, _solid_id, face_id, edge_id = _attach_demo_shape(project)
    binding = bind_topology_material_phase(project)
    assert binding.ok

    index = build_topology_identity_index(project, attach=True)
    summary = index.summary()
    assert summary["shape_count"] >= 1
    assert summary["face_count"] >= 1
    assert summary["edge_count"] >= 1
    assert summary["lineage_count"] >= 1
    assert index.lookup_by_topology_id[face_id] == f"topology:face:{shape_id}:{face_id}"

    face_identity = index.topology_by_id(face_id)
    assert face_identity is not None
    assert face_identity.source_entity_id == volume_id
    assert face_identity.material_id
    assert "initial" in face_identity.phase_ids
    assert face_identity.confidence in {"native", "certified"}

    selection = index.resolve_pick_metadata({"topology_id": face_id, "shape_id": shape_id, "topology_kind": "face"})
    assert selection.has_topology
    assert selection.active_key == face_identity.key
    assert selection.active_topology_id == face_id

    validation = validate_topology_identity_index(project, require_faces=True, require_edges=True)
    assert validation["ok"] is True
    assert project.metadata["topology_identity_index"]["summary"]["face_count"] >= 1


def test_p7_viewport_pick_selection_keeps_canonical_topology_key():
    project = load_demo_project("foundation_pit_3d_beta")
    _volume_id, shape_id, _solid_id, face_id, edge_id = _attach_demo_shape(project)
    state = ViewportState()
    state.update_from_geoproject_document(project)

    face_primitive = next(p for p in state.primitives.values() if p.entity_id == face_id)
    edge_primitive = next(p for p in state.primitives.values() if p.entity_id == edge_id)
    assert face_primitive.metadata["topology_identity_key"] == f"topology:face:{shape_id}:{face_id}"
    assert edge_primitive.metadata["topology_identity_key"] == f"topology:edge:{shape_id}:{edge_id}"

    face_pick = pick_by_entity_id(state, face_id, entity_kind="face")
    assert face_pick.metadata["selection_key"] == f"topology:face:{shape_id}:{face_id}"

    class Event:
        world = (1.0, 2.0, 3.0)
        metadata = {"topology_id": edge_id, "shape_id": shape_id, "topology_kind": "edge"}

    event_pick = pick_from_tool_event(Event())
    assert event_pick.kind == "edge"
    assert event_pick.entity_id == edge_id
    assert event_pick.metadata["topology_identity_key"] == f"topology:edge:{shape_id}:{edge_id}"

    controller = SelectionController()
    controller.select(face_id, "face", metadata=face_pick.metadata)
    controller.select(edge_id, "edge", mode="add", metadata=event_pick.metadata)
    payload = controller.to_dict()
    assert face_id in payload["selected_ids"]
    assert edge_id in payload["selected_ids"]
    assert f"topology:face:{shape_id}:{face_id}" in payload["selected_keys"]
    assert f"topology:edge:{shape_id}:{edge_id}" in payload["selected_keys"]


def test_p7_topology_identity_command_is_undoable():
    project = load_demo_project("foundation_pit_3d_beta")
    _attach_demo_shape(project)
    stack = CommandStack()
    result = stack.execute(BuildTopologyIdentityIndexCommand(require_faces=True, require_edges=True), project)
    assert result.ok
    assert result.metadata["validation"]["ok"] is True
    assert "topology_identity_index" in project.metadata
    undo = stack.undo(project)
    assert undo.ok


def test_p7_resolve_topology_selection_returns_empty_for_unknown_pick():
    project = load_demo_project("foundation_pit_3d_beta")
    _attach_demo_shape(project)
    selection = resolve_topology_selection(project, {"topology_id": "missing"})
    assert selection.has_topology is False
    assert selection.active_kind == "empty"


def _imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    rows: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            rows.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            rows.add(node.module)
    return rows


def test_p7_identity_core_and_service_are_headless_boundaries():
    core_imports = _imports("src/geoai_simkit/core/topology_identity.py")
    service_imports = _imports("src/geoai_simkit/services/topology_identity_service.py")
    forbidden_core = {"geoai_simkit.app", "geoai_simkit.services", "geoai_simkit.geoproject", "PySide6", "pyvista", "vtk", "OCP", "ifcopenshell", "gmsh", "meshio"}
    forbidden_service = {"geoai_simkit.app", "PySide6", "pyvista", "vtk", "OCP", "ifcopenshell", "gmsh", "meshio"}
    assert not any(item == bad or item.startswith(bad + ".") for item in core_imports for bad in forbidden_core)
    assert not any(item == bad or item.startswith(bad + ".") for item in service_imports for bad in forbidden_service)
