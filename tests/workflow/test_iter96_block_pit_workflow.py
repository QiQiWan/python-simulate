from __future__ import annotations


def test_foundation_pit_block_workflow_contract():
    from geoai_simkit.geometry.foundation_pit_blocks import build_foundation_pit_blocks

    artifact = build_foundation_pit_blocks({"dimension": "3d", "depth": 9.0})
    summary = artifact["summary"]
    assert summary["block_count"] >= 20
    assert summary["excavation_block_count"] == 3
    assert summary["wall_block_count"] == 4
    assert summary["contact_pair_count"] > 0
    assert summary["interface_request_count"] > 0
    assert {row["request_type"] for row in artifact["interface_requests"]} >= {"node_pair_contact", "release_boundary"}
    assert len(artifact["face_tags"]) == summary["face_tag_count"]


def test_block_pit_case_preserves_tags_and_stage_results():
    from geoai_simkit.examples.block_pit_workflow import build_block_pit_case
    from geoai_simkit.pipeline.runner import AnalysisTaskSpec, GeneralFEMSolver

    case = build_block_pit_case(dimension="3d", smoke=True)
    result = GeneralFEMSolver().run(AnalysisTaskSpec(case=case))
    model = result.prepared.model
    assert result.accepted is True
    assert "block_tag" in model.mesh.cell_data
    assert "face_tags_json" in model.mesh.field_data
    assert len(model.metadata["foundation_pit.interface_requests"]) > 0
    assert all("activation_map" in stage.metadata for stage in model.stages)
    metrics = model.metadata["stage_result_metrics"]
    assert metrics[-1]["max_wall_horizontal_displacement_mm"] > metrics[1]["max_wall_horizontal_displacement_mm"]
    assert metrics[-1]["max_surface_settlement_mm"] < 0.0
    labels = model.list_result_labels()
    assert "wall_horizontal_displacement@excavate_level_03" in labels
    assert "surface_settlement@excavate_level_03" in labels
