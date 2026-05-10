from __future__ import annotations

from geoai_simkit.adapters import make_project_context
from geoai_simkit.contracts import (
    ProjectReadPort,
    project_compiled_phase_summary,
    project_geometry_summary,
    project_material_summary,
    project_mesh_summary,
    project_result_store_summary,
    project_stage_summary,
)
from geoai_simkit.modules import document_model
from geoai_simkit.modules.fem_solver import solve_project, solver_backend_registry
from geoai_simkit.services import run_project_workflow


def test_project_context_exposes_strict_summary_ports() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="strict-port")
    port = make_project_context(project)

    assert isinstance(port, ProjectReadPort)
    geometry = project_geometry_summary(port)
    mesh = project_mesh_summary(port)
    stages = project_stage_summary(port)
    materials = project_material_summary(port)
    results = project_result_store_summary(port)
    phases = project_compiled_phase_summary(port)

    assert geometry.geometry_count >= 1
    assert isinstance(mesh.to_dict(), dict)
    assert stages.stage_count >= 1
    assert materials.material_count >= 0
    assert results.stage_count >= 0
    assert phases.compiled is True


def test_linear_static_cpu_backend_is_real_registered_solver_backend() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="linear-static")
    keys = solver_backend_registry().keys()
    assert "reference_cpu" in keys
    assert "linear_static_cpu" in keys

    result = solve_project(project, backend_preference="linear_static_cpu")
    assert result.ok is True
    assert result.backend_key == "linear_static_cpu"
    assert result.metadata["benchmark"]["contract"] == "sparse_linear_static_v1"
    assert result.metadata["benchmark"]["passed"] is True


def test_canonical_workflow_can_route_to_second_solver_backend() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="linear-workflow")
    report = run_project_workflow(project, mesh_kind="auto", solver_backend="linear_static_cpu", summarize=False)

    assert report.artifacts["solve"].backend_key == "linear_static_cpu"
    assert next(step for step in report.steps if step.key == "fem_solver").ok is True
    assert [step.key for step in report.steps] == ["project_port", "meshing", "stage_planning", "fem_solver"]
