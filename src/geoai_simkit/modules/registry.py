from __future__ import annotations

"""Registry for the coarse project modules used by update workflows."""

from importlib import import_module
from typing import Any

from geoai_simkit.modules.contracts import ProjectModuleSpec


PROJECT_MODULE_SPECS: tuple[ProjectModuleSpec, ...] = (
    ProjectModuleSpec(
        key="document_model",
        label="Project document model",
        responsibility="Shared GeoProjectDocument state, validation and serialization boundary.",
        owned_namespaces=("geoai_simkit.geoproject", "geoai_simkit.document", "geoai_simkit.contracts.project"),
        public_entrypoints=("create_empty_project", "create_foundation_pit_project", "validate_project"),
        depends_on=(),
        boundary_notes=(
            "Owns persistent project state shared by import, GUI, solver and result modules.",
            "Must stay dependency-light so it can be imported by tests and headless tools.",
        ),
    ),
    ProjectModuleSpec(
        key="geology_import",
        label="Geological import",
        responsibility="STL/geological model loading, diagnostics and conversion into project documents.",
        owned_namespaces=("geoai_simkit.geology.importers", "geoai_simkit.geometry.stl_loader", "geoai_simkit.contracts.geology"),
        public_entrypoints=(
            "import_geology",
            "create_project_from_geology",
            "supported_geology_import_kinds",
            "load_geological_stl",
            "create_project_from_stl",
            "import_stl_into_project",
        ),
        depends_on=("document_model",),
        boundary_notes=(
            "Writes geometry, soil, material and mesh records through document adapters/contracts.",
            "Must not depend on GUI widgets or solver internals.",
        ),
    ),
    ProjectModuleSpec(
        key="meshing",
        label="Meshing",
        responsibility="Mesh generation, mesh attachment and quality handoff through MeshRequest/MeshResult contracts.",
        owned_namespaces=("geoai_simkit.mesh", "geoai_simkit.contracts.mesh", "geoai_simkit.adapters.mesh_adapters"),
        public_entrypoints=("generate_project_mesh", "current_project_mesh", "supported_mesh_generators", "mesh_generator_registry"),
        depends_on=("document_model", "geology_import"),
        boundary_notes=(
            "Mesh generators are registered adapters and must not import GUI or solver internals.",
            "Downstream modules consume MeshResult rather than mesher-specific return types.",
        ),
    ),
    ProjectModuleSpec(
        key="stage_planning",
        label="Stage planning",
        responsibility="Stage plan summaries, active block queries and phase compilation through StageCompileResult.",
        owned_namespaces=("geoai_simkit.stage", "geoai_simkit.contracts.stage"),
        public_entrypoints=("compile_project_stages", "list_project_stages", "active_blocks_for_stage", "stage_compiler_descriptors"),
        depends_on=("document_model", "meshing"),
        boundary_notes=(
            "Compiles stage state for solver handoff without importing solver backends.",
            "GUI commands may edit stages, but service/facade calls expose stable stage contracts.",
        ),
    ),
    ProjectModuleSpec(
        key="gui_modeling",
        label="GUI modeling",
        responsibility="Workbench, tools, viewport state and non-interactive modeling session setup.",
        owned_namespaces=("geoai_simkit.app", "geoai_simkit.commands"),
        public_entrypoints=("create_headless_modeling_session", "build_modeling_architecture_payload"),
        depends_on=("document_model", "postprocessing"),
        boundary_notes=(
            "GUI code should call core services through facades or controllers.",
            "Headless entrypoints must avoid importing optional Qt/PyVista dependencies.",
        ),
    ),
    ProjectModuleSpec(
        key="fem_solver",
        label="Finite element solver",
        responsibility="Core FEM contracts, phase compilation and executable staged solve entrypoints.",
        owned_namespaces=("geoai_simkit.fem", "geoai_simkit.solver", "geoai_simkit.contracts.solver"),
        public_entrypoints=("compile_project_phases", "solve_project", "run_project_incremental_solve", "solver_backend_registry", "run_core_fem_smoke"),
        depends_on=("document_model", "meshing", "stage_planning"),
        boundary_notes=(
            "Owns numerical assembly/solve workflows and writes results through documented result records.",
            "Solver implementations are selected through SolverBackendRegistry and must not import GUI widgets or rendering modules.",
        ),
    ),
    ProjectModuleSpec(
        key="geotechnical",
        label="Geotechnical analysis",
        responsibility="Production-facing geotechnical readiness, material/interface summaries and staged nonlinear workflow facade.",
        owned_namespaces=("geoai_simkit.contracts.geotechnical", "geoai_simkit.services.geotechnical_readiness", "geoai_simkit.modules.geotechnical"),
        public_entrypoints=("geotechnical_state", "readiness_report", "run_staged_geotechnical_analysis"),
        depends_on=("document_model", "meshing", "stage_planning", "fem_solver", "postprocessing"),
        boundary_notes=(
            "Aggregates Project Port v2 engineering summaries and readiness reports without importing GUI or solver internals.",
            "Staged workflows must route through services/workflow_service and public module facades.",
        ),
    ),
    ProjectModuleSpec(
        key="postprocessing",
        label="Result postprocessing",
        responsibility="Result stores, packages, summaries and preview builder access.",
        owned_namespaces=("geoai_simkit.results", "geoai_simkit.post", "geoai_simkit.contracts.results"),
        public_entrypoints=("build_project_result_summary", "build_result_database_for_model", "summarize_results", "postprocessor_registry", "create_preview_builder"),
        depends_on=("document_model", "fem_solver"),
        boundary_notes=(
            "Reads solver outputs and result packages without reaching into solver internals.",
            "Visualization helpers must keep heavy rendering imports lazy.",
        ),
    ),
)

_SPECS_BY_KEY = {spec.key: spec for spec in PROJECT_MODULE_SPECS}


def get_project_module(key: str) -> ProjectModuleSpec:
    try:
        return _SPECS_BY_KEY[str(key)]
    except KeyError as exc:
        known = ", ".join(sorted(_SPECS_BY_KEY))
        raise KeyError(f"Unknown project module {key!r}. Known modules: {known}") from exc


def list_project_modules() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in PROJECT_MODULE_SPECS]


def module_update_map() -> dict[str, dict[str, Any]]:
    return {
        spec.key: {
            "label": spec.label,
            "responsibility": spec.responsibility,
            "owned_namespaces": list(spec.owned_namespaces),
            "entrypoints": list(spec.public_entrypoints),
            "depends_on": list(spec.depends_on),
        }
        for spec in PROJECT_MODULE_SPECS
    }


def run_project_module_smokes() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for spec in PROJECT_MODULE_SPECS:
        module = import_module(f"geoai_simkit.modules.{spec.key}")
        checks.append(module.smoke_check())
    return {
        "suite": "project_module_facade_smoke",
        "ok": all(row.get("ok") for row in checks),
        "check_count": len(checks),
        "passed_count": sum(1 for row in checks if row.get("ok")),
        "checks": checks,
    }


__all__ = [
    "PROJECT_MODULE_SPECS",
    "get_project_module",
    "list_project_modules",
    "module_update_map",
    "run_project_module_smokes",
]
