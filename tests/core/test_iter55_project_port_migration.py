from __future__ import annotations

from geoai_simkit.adapters import make_project_context
from geoai_simkit.contracts import ProjectReadPort, ProjectResourceSummary, ProjectWritePort
from geoai_simkit.modules import document_model
from geoai_simkit.modules.fem_solver import solve_project
from geoai_simkit.modules.postprocessing import summarize_results
from geoai_simkit.modules.stage_planning import compile_project_stages, list_project_stages


def test_project_context_is_read_write_port_with_resource_summary() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="port-smoke")
    context = make_project_context(project, source="iter55")

    assert isinstance(context, ProjectReadPort)
    assert isinstance(context, ProjectWritePort)
    assert context.snapshot().name == "port-smoke"
    resources = context.resource_summary()
    assert isinstance(resources, ProjectResourceSummary)
    assert resources.stage_ids
    assert context.get_project() is project


def test_module_facades_accept_project_ports_instead_of_raw_documents() -> None:
    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="port-facade")
    port = make_project_context(project)

    stages = compile_project_stages(port)
    solve = solve_project(port, backend_preference="reference_cpu")
    summary = summarize_results(port, processor="project_result_summary")

    assert stages.ok is True
    assert list_project_stages(port)
    assert solve.backend_key == "reference_cpu"
    assert summary.accepted is True
