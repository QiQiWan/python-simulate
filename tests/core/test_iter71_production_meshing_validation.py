from __future__ import annotations

from geoai_simkit.examples.verified_3d import build_tetra_column_project, run_verified_tetra_column
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import geotechnical, meshing
from geoai_simkit.services import build_production_meshing_validation_report, optional_mesher_dependency_status, run_project_workflow


def test_optional_mesher_dependency_status_is_stable() -> None:
    status = optional_mesher_dependency_status().to_dict()
    assert status["metadata"]["contract"] == "optional_mesher_dependency_status_v1"
    assert "production_tet4_available" in status
    assert status["status"] in {"available", "missing_optional_dependency"}


def test_stl_repair_report_flags_surface_before_volume_meshing(tmp_path) -> None:
    from geoai_simkit.examples.verified_3d import write_tetra_stl

    stl = write_tetra_stl(tmp_path / "surface.stl")
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "repair-surface", "material_id": "rock"})

    report = meshing.analyze_stl_repair_readiness(project)
    assert report["metadata"]["contract"] == "stl_repair_report_v1"
    assert report["region_count"] == 1
    assert report["closed_region_count"] == 1
    assert report["open_boundary_edge_count"] == 0


def test_production_meshing_validation_accepts_verified_volume_project(tmp_path) -> None:
    project = build_tetra_column_project(tmp_path)

    report = build_production_meshing_validation_report(project, solver_backend="solid_linear_static_cpu")
    data = report.to_dict()

    assert report.ok is True
    assert data["metadata"]["contract"] == "production_meshing_validation_report_v1"
    assert data["mesh_quality"]["ok"] is True
    assert data["material_compatibility"]["ok"] is True
    assert data["region_quality"]
    assert data["region_quality"][0]["ok"] is True
    assert meshing.production_meshing_validation(project)["ok"] is True
    assert geotechnical.production_meshing_validation(project)["ok"] is True


def test_workflow_manifest_contains_mesh_validation_quality_artifact(tmp_path) -> None:
    result = run_verified_tetra_column(tmp_path)
    manifest = result["workflow"]["artifact_manifest"]
    keys = [item["key"] for item in manifest["artifacts"]]
    kinds = {item["key"]: item["kind"] for item in manifest["artifacts"]}

    assert "mesh_validation" in keys
    assert kinds["mesh_validation"] == "quality"
    validation = next(item for item in manifest["artifacts"] if item["key"] == "mesh_validation")
    assert validation["metadata"]["legacy_payload_available"] is True


def test_run_project_workflow_adds_production_validation_artifact_without_changing_legacy_step_order(tmp_path) -> None:
    project = build_tetra_column_project(tmp_path)
    report = run_project_workflow(project, mesh_kind="auto", solver_backend="solid_linear_static_cpu", summarize=True, metadata={"include_mesh_validation_artifact": True})
    step_keys = [step.key for step in report.steps]
    assert step_keys == ["project_port", "meshing", "stage_planning", "fem_solver", "postprocessing"]
    assert report.artifact_ref("mesh_validation") is not None
