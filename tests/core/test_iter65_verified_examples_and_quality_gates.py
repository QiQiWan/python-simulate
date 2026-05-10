from __future__ import annotations

from geoai_simkit.examples.verified_3d import build_tetra_column_project, run_verified_multi_region, run_verified_tetra_column
from geoai_simkit.modules import geotechnical, meshing
from geoai_simkit.services import build_geotechnical_quality_gate, evaluate_material_compatibility, evaluate_mesh_quality_gate


def test_mesh_quality_and_material_gates_accept_verified_tet4_project(tmp_path) -> None:
    project = build_tetra_column_project(tmp_path)

    mesh_gate = evaluate_mesh_quality_gate(project)
    material_gate = evaluate_material_compatibility(project, solver_backend="solid_linear_static_cpu")
    combined = build_geotechnical_quality_gate(project, solver_backend="solid_linear_static_cpu")

    assert mesh_gate.ok is True
    assert mesh_gate.solid_cell_count == 1
    assert material_gate.ok is True
    assert combined.ok is True
    assert meshing.evaluate_project_mesh_quality(project)["ok"] is True


def test_geotechnical_facade_exposes_quality_gate_and_project_state_v3(tmp_path) -> None:
    project = build_tetra_column_project(tmp_path)

    state = geotechnical.geotechnical_state(project)
    gate = geotechnical.quality_gate(project, solver_backend="solid_linear_static_cpu")

    assert state["contract"] == "geotechnical_state_v1"
    assert state["contract_version"] == "geotechnical_state_v3"
    assert state["metadata"]["contract"] == "project_engineering_state_v3"
    assert gate["ok"] is True
    assert gate["metadata"]["contract"] == "geotechnical_quality_gate_v1"


def test_verified_3d_example_suite_runs_headless_and_exports_manifest(tmp_path) -> None:
    tetra = run_verified_tetra_column(tmp_path / "tetra")
    multi = run_verified_multi_region(tmp_path / "multi")

    assert tetra["ok"] is True
    assert tetra["workflow"]["artifact_manifest"]["metadata"]["contract"] == "workflow_artifact_manifest_v2"
    assert multi["ok"] is True
    assert multi["quality_gate"]["ok"] is True
    assert multi["workflow"]["artifact_manifest"]["artifact_count"] >= 4
