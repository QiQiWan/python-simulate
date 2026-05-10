from __future__ import annotations

from geoai_simkit.contracts import WorkflowArtifactRef
from geoai_simkit.modules import document_model
from geoai_simkit.modules.example_plugins import DummyMeshGenerator, DummyPostProcessor, DummySolverBackend
from geoai_simkit.modules.fem_solver import register_solver_backend
from geoai_simkit.modules.meshing import register_mesh_generator
from geoai_simkit.modules.postprocessing import register_postprocessor
from geoai_simkit.services import run_project_workflow


def test_workflow_report_exposes_typed_artifact_refs_without_breaking_legacy_payloads() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="iter63-artifacts")
    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)

    report = run_project_workflow(
        project,
        mesh_kind="dummy_mesh",
        solver_backend="dummy_solver",
        postprocessor="dummy_postprocessor",
        metadata={"case": "iter63"},
    )

    assert report.ok is True
    assert report.artifacts["solve"].backend_key == "dummy_solver"  # legacy compatibility
    assert {item.key for item in report.artifact_refs} == {"mesh", "stages", "solve", "summary"}
    assert all(isinstance(item, WorkflowArtifactRef) for item in report.artifact_refs)

    solve_ref = report.artifact_ref("solve")
    assert solve_ref is not None
    assert solve_ref.kind == "solve"
    assert solve_ref.producer == "fem_solver"
    assert solve_ref.summary["backend_key"] == "dummy_solver"
    assert solve_ref.metadata["contract"] == "workflow_artifact_ref_v1"

    payload = report.to_dict()
    assert payload["metadata"]["workflow_artifacts_contract"] == "workflow_artifact_ref_v1"
    assert any(item["key"] == "summary" and item["kind"] == "summary" for item in payload["artifact_refs"])


def test_workflow_artifact_controller_returns_gui_table_rows() -> None:
    from geoai_simkit.app.controllers import WorkflowArtifactActionController

    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="iter63-artifact-controller")
    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)
    report = run_project_workflow(project, mesh_kind="dummy_mesh", solver_backend="dummy_solver", postprocessor="dummy_postprocessor")

    rows = WorkflowArtifactActionController(report).artifact_table_rows()

    assert len(rows) == 4
    assert {row["kind"] for row in rows} >= {"mesh", "stages", "solve", "summary"}
    assert all("payload_type" in row for row in rows)
