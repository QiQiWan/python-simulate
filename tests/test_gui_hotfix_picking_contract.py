from __future__ import annotations

from geoai_simkit.app.viewport.selection_controller import SelectionController
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.geoproject.cad_shape_store import CadOperationHistoryRecord, CadShapeRecord, CadTopologyRecord
from geoai_simkit.services.boolean_topology_lineage import build_boolean_topology_lineage
from geoai_simkit.services.demo_project_runner import load_demo_project


def test_selection_controller_exposes_current_selection():
    controller = SelectionController()
    controller.select("face:demo:xmin", "face", metadata={"topology_id": "face:demo:xmin"})
    current = controller.current_selection()
    assert len(current.items) == 1
    assert current.items[0].kind == "face"
    assert current.items[0].metadata["topology_id"] == "face:demo:xmin"


def test_viewport_state_adds_pickable_cad_face_edge_records():
    project = load_demo_project("foundation_pit_3d_beta")
    volume_id = next(iter(project.geometry_model.volumes))
    bounds = project.geometry_model.volumes[volume_id].bounds
    shape_id = "shape:test_volume"
    face_id = "face:test_volume:xmin"
    edge_id = "edge:test_volume:bottom_0"
    project.cad_shape_store.shapes[shape_id] = CadShapeRecord(
        id=shape_id,
        name=shape_id,
        source_entity_ids=[volume_id],
        topology_ids=[face_id, edge_id],
    )
    project.cad_shape_store.topology_records[face_id] = CadTopologyRecord(
        id=face_id,
        shape_id=shape_id,
        kind="face",
        source_entity_id=volume_id,
        bounds=(bounds[0], bounds[0], bounds[2], bounds[3], bounds[4], bounds[5]),
        orientation="xmin",
    )
    project.cad_shape_store.topology_records[edge_id] = CadTopologyRecord(
        id=edge_id,
        shape_id=shape_id,
        kind="edge",
        source_entity_id=volume_id,
        bounds=(bounds[0], bounds[1], bounds[2], bounds[2], bounds[4], bounds[4]),
        orientation="bottom_x",
    )
    state = ViewportState()
    state.update_from_geoproject_document(project)
    assert any(p.entity_id == face_id and p.kind == "face" for p in state.primitives.values())
    assert any(p.entity_id == edge_id and p.kind == "edge" for p in state.primitives.values())
    block = state.primitives[f"primitive:block:{volume_id}"]
    assert face_id in block.metadata["topology_face_ids"]
    assert edge_id in block.metadata["topology_edge_ids"]


def test_boolean_lineage_consumes_native_occ_history_map():
    project = load_demo_project("foundation_pit_3d_beta")
    volume_id = next(iter(project.geometry_model.volumes))
    shape_in = "shape:in"
    shape_out = "shape:out"
    face_in = "face:in:xmin"
    face_out_a = "face:out:xmin_a"
    face_out_b = "face:out:xmin_b"
    project.cad_shape_store.shapes[shape_in] = CadShapeRecord(id=shape_in, name=shape_in, source_entity_ids=[volume_id], topology_ids=[face_in])
    project.cad_shape_store.shapes[shape_out] = CadShapeRecord(id=shape_out, name=shape_out, source_entity_ids=[volume_id], topology_ids=[face_out_a, face_out_b])
    for tid, shape_id in [(face_in, shape_in), (face_out_a, shape_out), (face_out_b, shape_out)]:
        project.cad_shape_store.topology_records[tid] = CadTopologyRecord(id=tid, shape_id=shape_id, kind="face", source_entity_id=volume_id, orientation="xmin")
    project.cad_shape_store.operation_history["op:native"] = CadOperationHistoryRecord(
        id="op:native",
        operation="boolean_fragment",
        input_shape_ids=[shape_in],
        output_shape_ids=[shape_out],
        native_backend_used=True,
        fallback_used=False,
        metadata={
            "native_occ_history_map": [
                {
                    "operation_id": "op:native",
                    "topology_kind": "face",
                    "lineage_type": "split",
                    "input_topology_ids": [face_in],
                    "output_topology_ids": [face_out_a, face_out_b],
                }
            ]
        },
    )
    report = build_boolean_topology_lineage(project, overwrite=True)
    assert report.ok
    assert report.native_lineage_count == 1
    assert report.split_count >= 1
    row = next(iter(project.cad_shape_store.topology_lineage.values()))
    assert row.confidence == "native"
    assert row.input_topology_ids == [face_in]
    assert row.output_topology_ids == [face_out_a, face_out_b]
