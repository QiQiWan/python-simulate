from __future__ import annotations

from geoai_simkit.contracts import ProjectEngineeringState, WorkflowArtifactManifest, project_engineering_state
from geoai_simkit.modules import document_model
from geoai_simkit.modules.example_plugins import DummyMeshGenerator, DummyPostProcessor, DummySolverBackend
from geoai_simkit.modules.fem_solver import register_solver_backend
from geoai_simkit.modules.meshing import register_mesh_generator
from geoai_simkit.modules.postprocessing import register_postprocessor
from geoai_simkit.services import run_project_workflow


def test_project_engineering_state_v3_is_serializable() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="iter64-port-v3")
    state = project_engineering_state(project)
    payload = state.to_dict()

    assert isinstance(state, ProjectEngineeringState)
    assert payload["metadata"]["contract"] == "project_engineering_state_v3"
    assert "solid_mesh" in payload
    assert "material" in payload
    assert "readiness" in payload


def test_workflow_artifact_manifest_v2_tracks_lineage_while_legacy_payloads_remain() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="iter64-manifest")
    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)

    report = run_project_workflow(
        project,
        mesh_kind="dummy_mesh",
        solver_backend="dummy_solver",
        postprocessor="dummy_postprocessor",
        metadata={"workflow_id": "iter64_manifest"},
    )
    manifest = report.artifact_manifest()
    payload = report.to_dict()

    assert report.artifacts["solve"].backend_key == "dummy_solver"
    assert isinstance(manifest, WorkflowArtifactManifest)
    assert manifest.manifest_id == "iter64_manifest:manifest"
    assert len(manifest.lineage) == 4
    assert payload["artifact_manifest"]["metadata"]["contract"] == "workflow_artifact_manifest_v2"
    assert payload["metadata"]["workflow_artifacts_contract"] == "workflow_artifact_ref_v1"
    assert payload["metadata"]["workflow_artifact_manifest_contract"] == "workflow_artifact_manifest_v2"
