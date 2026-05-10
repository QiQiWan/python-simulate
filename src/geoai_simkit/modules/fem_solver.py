from __future__ import annotations

"""Stable facade for finite-element solve workflows."""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import SolveRequest, SolveResult, project_compiled_phase_summary
from geoai_simkit.fem.api import get_core_fem_api_contracts, run_core_fem_api_smoke
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module
from geoai_simkit.solver.backend_registry import get_default_solver_backend_registry, register_solver_backend, solver_backend_capabilities

MODULE_KEY = "fem_solver"


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def compile_project_phases(project: Any) -> dict[str, Any]:
    context = as_project_context(project)
    summary = project_compiled_phase_summary(context)
    project_doc = context.get_project()
    compile_fn = getattr(project_doc, "compile_phase_models", None)
    if callable(compile_fn):
        return compile_fn()
    return summary.to_dict()


def solver_backend_registry():
    return get_default_solver_backend_registry()


def solve_project(
    project: Any,
    *,
    compile_if_needed: bool = True,
    write_results: bool = True,
    backend_preference: str = "reference_cpu",
    settings: Any = None,
    metadata: dict[str, Any] | None = None,
) -> SolveResult:
    request = SolveRequest(
        project=as_project_context(project),
        compile_if_needed=compile_if_needed,
        write_results=write_results,
        backend_preference=backend_preference,
        settings=settings,
        metadata=dict(metadata or {}),
    )
    backend = solver_backend_registry().resolve(request)
    return backend.solve(request)


def run_project_incremental_solve(
    project: Any,
    *,
    compile_if_needed: bool = True,
    write_results: bool = True,
) -> Any:
    """Backward-compatible summary-returning staged solve entrypoint."""

    result = solve_project(
        project,
        compile_if_needed=compile_if_needed,
        write_results=write_results,
        backend_preference="reference_cpu",
    )
    return result.summary if result.summary is not None else result


def run_core_fem_smoke() -> dict[str, Any]:
    return run_core_fem_api_smoke()


def smoke_check() -> dict[str, Any]:
    smoke = run_core_fem_smoke()
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "core_contract_count": len(get_core_fem_api_contracts()) == 7,
            "core_smoke_ok": bool(smoke.get("ok")),
            "solver_backend_registry": "reference_cpu" in solver_backend_registry().keys(),
        },
    )


__all__ = [
    "SolveRequest",
    "SolveResult",
    "compile_project_phases",
    "describe_module",
    "get_core_fem_api_contracts",
    "register_solver_backend",
    "run_core_fem_smoke",
    "run_project_incremental_solve",
    "smoke_check",
    "solve_project",
    "solver_backend_capabilities",
    "solver_backend_registry",
]
