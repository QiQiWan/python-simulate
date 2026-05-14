from __future__ import annotations

"""GUI-facing payloads for the 0.9 Alpha staged foundation-pit showcase."""

from pathlib import Path
from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.examples.alpha_0_9_workflow import build_alpha_foundation_pit_project, export_alpha_workflow_bundle, run_alpha_foundation_pit_workflow
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.system_audit import audit_geoproject_alpha


def build_alpha_showcase_payload(document: Any | None = None) -> dict[str, Any]:
    project = build_alpha_foundation_pit_project() if document is None else get_geoproject_document(document)
    validation = validate_geoproject_model(project, require_mesh=project.mesh_model.mesh_document is not None, require_results=bool(project.result_store.phase_results))
    compiler = compile_phase_solver_inputs(project, block_on_errors=False) if project.mesh_model.mesh_document is not None else None
    audit = audit_geoproject_alpha(project) if project.result_store.phase_results else None
    phases = project.phases_in_order()
    return {
        "contract": "alpha_0_9_showcase_panel_v1",
        "title": "GeoAI SimKit 0.9 Alpha - staged foundation pit",
        "phase_rows": [
            {
                "phase_id": stage.id,
                "name": stage.name,
                "predecessor_id": stage.predecessor_id,
                "active_volume_count": len(project.phase_manager.phase_state_snapshots.get(stage.id, project.refresh_phase_snapshot(stage.id)).active_volume_ids),
                "active_structure_count": len(project.phase_manager.phase_state_snapshots.get(stage.id, project.refresh_phase_snapshot(stage.id)).active_structure_ids),
                "water_level": stage.water_level,
            }
            for stage in phases
        ],
        "counts": validation.counts,
        "readiness": validation.readiness,
        "validation": validation.to_dict(),
        "compiler": None if compiler is None else compiler.to_dict(),
        "audit": None if audit is None else audit.to_dict(),
        "actions": ["build_alpha_foundation_pit_project", "run_alpha_foundation_pit_workflow", "export_alpha_workflow_bundle"],
    }


def create_alpha_showcase_project(document: Any | None = None) -> dict[str, Any]:
    project = build_alpha_foundation_pit_project()
    if document is not None:
        try:
            target = get_geoproject_document(document)
            restored = project
            for field_name in target.__dataclass_fields__:
                setattr(target, field_name, getattr(restored, field_name))
            mark_geoproject_dirty(document, target)
        except Exception:
            pass
    return {"ok": True, "project": project, "payload": build_alpha_showcase_payload(project)}


def run_alpha_showcase(document: Any | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    if document is None:
        return run_alpha_foundation_pit_workflow(output_dir=output_dir)
    project = get_geoproject_document(document)
    if not project.geometry_model.volumes:
        project = build_alpha_foundation_pit_project()
    from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve

    validation = validate_geoproject_model(project, require_mesh=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=False)
    solver = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
    audit = audit_geoproject_alpha(project)
    artifacts = export_alpha_workflow_bundle(project, output_dir, validation=validation.to_dict(), compiler=compiler.to_dict(), solver_summary=solver.to_dict(), audit=audit.to_dict()) if output_dir is not None else None
    mark_geoproject_dirty(document, project)
    return {
        "contract": "alpha_0_9_showcase_run_v1",
        "ok": validation.ok and compiler.ok and bool(project.result_store.phase_results),
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "solver_summary": solver.to_dict(),
        "audit": audit.to_dict(),
        "artifacts": None if artifacts is None else artifacts.to_dict(),
        "payload": build_alpha_showcase_payload(project),
    }


__all__ = ["build_alpha_showcase_payload", "create_alpha_showcase_project", "run_alpha_showcase"]
