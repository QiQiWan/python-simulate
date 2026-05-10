from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.adapters import make_project_context
from geoai_simkit.contracts import (
    ProjectPortCapabilities,
    ProjectResourceSummary,
    ProjectSnapshot,
    ProjectWorkflowRequest,
    is_project_port,
    project_port_capabilities,
)
from geoai_simkit.modules import document_model
from geoai_simkit.modules.example_plugins import DummyMeshGenerator, DummyPostProcessor, DummySolverBackend
from geoai_simkit.modules.fem_solver import register_solver_backend
from geoai_simkit.modules.meshing import register_mesh_generator
from geoai_simkit.modules.postprocessing import register_postprocessor
from geoai_simkit.services import ProjectWorkflowService, run_project_workflow


@dataclass(slots=True)
class CustomReadOnlyPort:
    project: Any
    snapshots: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> ProjectSnapshot:
        self.snapshots += 1
        return ProjectSnapshot(project_id="custom", name="custom-port", metadata=self.metadata)

    def resource_summary(self) -> ProjectResourceSummary:
        return ProjectResourceSummary(metadata=self.metadata)

    def get_project(self) -> Any:
        return self.project

    def geometry_keys(self) -> tuple[str, ...]:
        return ()

    def stage_ids(self) -> tuple[str, ...]:
        return ()

    def result_stage_ids(self) -> tuple[str, ...]:
        return ()

    def current_mesh(self) -> Any:
        return None

    def port_capabilities(self) -> ProjectPortCapabilities:
        return ProjectPortCapabilities(readable=True, writable=False, transactional=False, legacy_document_access=True)


def test_custom_project_port_is_preserved_by_adapter_boundary() -> None:
    project = document_model.create_empty_project(name="wrapped")
    custom = CustomReadOnlyPort(project)

    assert is_project_port(custom) is True
    assert make_project_context(custom) is custom
    assert project_port_capabilities(custom).writable is False
    assert custom.snapshot().name == "custom-port"


def test_canonical_workflow_service_runs_through_registered_plugins() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="workflow-service")
    port = make_project_context(project)

    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)

    report = ProjectWorkflowService().run(
        ProjectWorkflowRequest(
            project=port,
            mesh_kind="dummy_mesh",
            solver_backend="dummy_solver",
            postprocessor="dummy_postprocessor",
            metadata={"test": "iter56"},
        )
    )

    assert report.ok is True
    assert report.snapshot_before is not None
    assert report.snapshot_after is not None
    assert [step.key for step in report.steps] == ["project_port", "meshing", "stage_planning", "fem_solver", "postprocessing"]
    assert report.artifacts["mesh"].metadata["plugin"] == "dummy_mesh"
    assert report.artifacts["solve"].backend_key == "dummy_solver"
    assert report.artifacts["summary"].metadata["plugin"] == "dummy_postprocessor"


def test_workflow_convenience_entrypoint_returns_serialisable_report() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="workflow-entrypoint")
    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)

    report = run_project_workflow(
        project,
        mesh_kind="dummy_mesh",
        solver_backend="dummy_solver",
        postprocessor="dummy_postprocessor",
    )
    payload = report.to_dict()

    assert payload["ok"] is True
    assert payload["metadata"]["solver_backend"] == "dummy_solver"
    assert "summary" in payload["artifact_keys"]
