from __future__ import annotations

"""Geotechnical module facade.

This facade is the stable module-level boundary for production-facing 3D
geotechnical workflows. It aggregates Project Port v2 summaries, readiness
checks and staged solve orchestration without exposing GUI or solver internals.
"""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts.geotechnical import (
    analysis_readiness_summary,
    boundary_condition_summary,
    interface_summary,
    load_summary,
    material_mapping_summary,
    solid_mesh_summary,
    stage_activation_summary,
)
from geoai_simkit.services.geotechnical_readiness import build_geotechnical_readiness_report
from geoai_simkit.services.quality_gates import build_geotechnical_quality_gate
from geoai_simkit.services.production_meshing_validation import build_production_meshing_validation_report
from geoai_simkit.contracts import project_engineering_state
from geoai_simkit.services.workflow_service import run_project_workflow


def geotechnical_state(project: Any) -> dict[str, Any]:
    """Return strict Project Port v3 engineering/geotechnical summaries.

    The legacy top-level v1 keys remain present for existing GUI/tests, while
    the full v3 aggregate is exposed under ``project_engineering_state``.
    """

    context = as_project_context(project)
    engineering = project_engineering_state(context).to_dict()
    legacy = {
        "solid_mesh": solid_mesh_summary(context).to_dict(),
        "material_mapping": material_mapping_summary(context).to_dict(),
        "boundary_conditions": boundary_condition_summary(context).to_dict(),
        "loads": load_summary(context).to_dict(),
        "interfaces": interface_summary(context).to_dict(),
        "stage_activation": stage_activation_summary(context).to_dict(),
        "analysis_readiness": analysis_readiness_summary(context).to_dict(),
    }
    return {
        **legacy,
        "project_engineering_state": engineering,
        "metadata": engineering.get("metadata", {}),
        "contract": "geotechnical_state_v1",
        "contract_version": "geotechnical_state_v3",
    }

def quality_gate(project: Any, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    """Return mesh/material/readiness gates for verified 3D geotechnical analysis."""

    return build_geotechnical_quality_gate(as_project_context(project), solver_backend=solver_backend).to_dict()



def production_meshing_validation(project: Any, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    """Return production STL/mesh/material/interface validation for geotechnical workflows."""

    return build_production_meshing_validation_report(as_project_context(project), solver_backend=solver_backend).to_dict()

def readiness_report(project: Any) -> dict[str, Any]:
    """Return the production geotechnical readiness report."""

    return build_geotechnical_readiness_report(as_project_context(project))


def run_staged_geotechnical_analysis(
    project: Any,
    *,
    mesh_kind: str = "auto",
    solver_backend: str = "staged_mohr_coulomb_cpu",
    load_increments: int = 3,
    max_iterations: int = 8,
    tolerance: float = 1.0e-5,
    summarize: bool = True,
    metadata: dict[str, Any] | None = None,
):
    """Run the canonical staged geotechnical workflow through public services."""

    workflow_metadata = {
        "load_increments": int(load_increments),
        "max_iterations": int(max_iterations),
        "tolerance": float(tolerance),
        "module": "geotechnical",
        **dict(metadata or {}),
    }
    return run_project_workflow(
        as_project_context(project),
        mesh_kind=mesh_kind,
        solver_backend=solver_backend,
        summarize=summarize,
        metadata=workflow_metadata,
    )


def contact_report(project: Any, *, max_active_set_iterations: int = 4, residual_tolerance: float = 1.0e-6, write_results: bool = True) -> dict[str, Any]:
    """Run Contact Solver Core v1 through the geotechnical module facade."""

    from geoai_simkit.solver.contact_core import ContactRunControl, run_project_contact_solver

    context = as_project_context(project)
    target = context.get_project() if hasattr(context, "get_project") else project
    report = run_project_contact_solver(
        target,
        control=ContactRunControl(
            max_active_set_iterations=max_active_set_iterations,
            residual_tolerance=residual_tolerance,
            write_results=write_results,
            metadata={"module": "geotechnical"},
        ),
        write_results=write_results,
    )
    return report.to_dict()


def smoke_check() -> dict[str, Any]:
    from geoai_simkit.modules.contracts import smoke_from_spec
    from geoai_simkit.modules.registry import get_project_module

    return smoke_from_spec(
        get_project_module("geotechnical"),
        checks={
            "state_entrypoint": callable(geotechnical_state),
            "readiness_entrypoint": callable(readiness_report),
            "workflow_entrypoint": callable(run_staged_geotechnical_analysis),
            "quality_gate_entrypoint": callable(quality_gate),
            "production_meshing_validation_entrypoint": callable(production_meshing_validation),
            "contact_report_entrypoint": callable(contact_report),
            "contract": "geotechnical_module_facade_v3",
        },
    )


__all__ = ["contact_report", "geotechnical_state", "production_meshing_validation", "quality_gate", "readiness_report", "run_staged_geotechnical_analysis", "smoke_check"]
