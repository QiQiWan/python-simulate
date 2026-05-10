from __future__ import annotations

from geoai_simkit.adapters import make_project_context, snapshot_project
from geoai_simkit.contracts import MeshRequest, ProjectContext, SolveRequest
from geoai_simkit.modules import document_model
from geoai_simkit.modules.fem_solver import solve_project, solver_backend_registry
from geoai_simkit.modules.meshing import supported_mesh_generators
from geoai_simkit.modules.stage_planning import compile_project_stages


def test_contracts_are_dependency_light_and_project_context_snapshots() -> None:
    project = document_model.create_empty_project(name="contracts-smoke")
    context = make_project_context(project, source="test")
    assert isinstance(context, ProjectContext)
    snapshot = context.snapshot()
    assert snapshot.name == "contracts-smoke"
    assert snapshot_project(project).project_id == project.project_settings.project_id


def test_p1_facades_exchange_contract_dtos() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="contract-pit")
    stage_result = compile_project_stages(project)
    solve_result = solve_project(project, compile_if_needed=True, write_results=True)

    assert stage_result.ok is True
    assert stage_result.stage_count >= 1
    assert solve_result.status in {"accepted", "rejected"}
    assert solve_result.backend_key == "reference_cpu"
    assert solve_result.summary is not None
    assert "reference_cpu" in solver_backend_registry().keys()
    assert supported_mesh_generators()


def test_contract_request_objects_are_stable() -> None:
    mesh_req = MeshRequest(project=object(), mesh_kind="auto", options={"nx": 2})
    solve_req = SolveRequest(project=object(), backend_preference="reference_cpu")
    assert mesh_req.mesh_kind == "auto"
    assert solve_req.backend_preference == "reference_cpu"
