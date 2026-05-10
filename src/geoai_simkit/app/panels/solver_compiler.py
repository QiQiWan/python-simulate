from __future__ import annotations

"""Solver compiler payloads backed by GeoProjectDocument.SolverModel."""

from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.geoproject import GeoProjectDocument, RuntimeSettings


def _compiled_summary(row: Any) -> dict[str, Any]:
    payload = row.to_dict()
    return {
        "id": payload["id"],
        "phase_id": payload["phase_id"],
        "active_cell_count": payload["active_cell_count"],
        "active_dof_count": payload["active_dof_count"],
        "material_state_count": payload["material_state_count"],
        "interface_count": payload["interface_count"],
        "block_presence": {
            "MeshBlock": bool(payload.get("MeshBlock")),
            "ElementBlock": bool(payload.get("ElementBlock")),
            "MaterialBlock": bool(payload.get("MaterialBlock")),
            "BoundaryBlock": bool(payload.get("BoundaryBlock")),
            "LoadBlock": bool(payload.get("LoadBlock")),
            "InterfaceBlock": bool(payload.get("InterfaceBlock")),
            "StateVariableBlock": bool(payload.get("StateVariableBlock")),
            "SolverControlBlock": bool(payload.get("SolverControlBlock")),
            "ResultRequestBlock": bool(payload.get("ResultRequestBlock")),
        },
        "metadata": dict(payload.get("metadata", {})),
    }


def build_geoproject_solver_compiler(project: GeoProjectDocument, *, compile_now: bool = False, include_full_blocks: bool = True) -> dict[str, Any]:
    if compile_now:
        project.compile_phase_models()
    compiled = list(project.solver_model.compiled_phase_models.values())
    missing_snapshots = [pid for pid in project.phase_ids() if pid not in project.phase_manager.phase_state_snapshots]
    readiness = {
        "ok": not missing_snapshots and bool(project.geometry_model.volumes),
        "missing_snapshots": missing_snapshots,
        "volume_count": len(project.geometry_model.volumes),
        "mesh_cell_count": 0 if project.mesh_model.mesh_document is None else project.mesh_model.mesh_document.cell_count,
        "material_count": len(project.material_library.material_ids()),
        "has_boundary_conditions": bool(project.solver_model.boundary_conditions),
        "has_loads": bool(project.solver_model.loads),
        "compiled_contract": "compiled_phase_model_input_skeleton_v2",
    }
    return {
        "contract": "geoproject_solver_compiler_v2",
        "data_source": "GeoProjectDocument.SolverModel",
        "runtime_settings": project.solver_model.runtime_settings.to_dict(),
        "boundary_conditions": [row.to_dict() for row in project.solver_model.boundary_conditions.values()],
        "loads": [row.to_dict() for row in project.solver_model.loads.values()],
        "phase_inputs": [
            {
                "phase_id": stage.id,
                "snapshot": None if stage.id not in project.phase_manager.phase_state_snapshots else project.phase_manager.phase_state_snapshots[stage.id].to_dict(),
                "calculation_settings": None if stage.id not in project.phase_manager.calculation_settings else project.phase_manager.calculation_settings[stage.id].to_dict(),
            }
            for stage in project.phases_in_order()
        ],
        "compiled_phase_models": [row.to_dict() for row in compiled] if include_full_blocks else [_compiled_summary(row) for row in compiled],
        "compiled_phase_summaries": [_compiled_summary(row) for row in compiled],
        "runtime_solver": dict(project.solver_model.metadata.get("last_incremental_solve", {}) or {}),
        "result_store_summary": {
            "phase_results": len(project.result_store.phase_results),
            "engineering_metrics": len(project.result_store.engineering_metrics),
            "curves": len(project.result_store.curves),
            "field_names": sorted({name for result in project.result_store.phase_results.values() for name in result.fields}),
        },
        "compile_readiness": readiness,
        "editable_actions": ["compile_phase_models", "run_incremental_solver", "update_runtime_settings", "add_boundary_condition", "add_load"],
    }


def build_solver_compiler(document: Any, *, compile_now: bool = False) -> dict[str, Any]:
    project = get_geoproject_document(document)
    payload = build_geoproject_solver_compiler(project, compile_now=compile_now)
    if compile_now:
        mark_geoproject_dirty(document, project)
    return payload


def compile_phase_models(document: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    project.populate_default_framework_content()
    compiled = project.compile_phase_models()
    mark_geoproject_dirty(document, project)
    return {"ok": True, "compiled_phase_models": [row.to_dict() for row in compiled.values()]}


def run_incremental_solver(document: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve

    project.populate_default_framework_content()
    summary = run_geoproject_incremental_solve(project, compile_if_needed=True, write_results=True)
    mark_geoproject_dirty(document, project)
    return {"ok": bool(summary.accepted), "summary": summary.to_dict(), "result_store": project.result_store.to_dict()}


def update_runtime_settings(document: Any, **kwargs: Any) -> dict[str, Any]:
    project = get_geoproject_document(document)
    payload = project.solver_model.runtime_settings.to_dict()
    payload.update(kwargs)
    payload.pop("metadata", None)
    metadata = dict(project.solver_model.runtime_settings.metadata)
    metadata.update(dict(kwargs.get("metadata", {}) or {}))
    project.solver_model.runtime_settings = RuntimeSettings.from_dict({**payload, "metadata": metadata})
    project.mark_changed(["solver"], action="update_runtime_settings")
    mark_geoproject_dirty(document, project)
    return {"ok": True, "runtime_settings": project.solver_model.runtime_settings.to_dict()}


__all__ = ["build_solver_compiler", "build_geoproject_solver_compiler", "compile_phase_models", "run_incremental_solver", "update_runtime_settings"]
