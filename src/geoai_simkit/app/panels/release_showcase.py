from __future__ import annotations

"""GUI-facing payloads for the 1.0 Basic engineering workflow."""

from pathlib import Path
from typing import Any

from geoai_simkit.app.geoproject_source import get_geoproject_document, mark_geoproject_dirty
from geoai_simkit.examples.release_1_0_workflow import build_release_1_0_project, export_release_1_0_bundle, run_release_1_0_workflow
from geoai_simkit.geoproject.runtime_solver import run_geoproject_incremental_solve
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.release_acceptance import audit_release_1_0


def build_release_1_0_showcase_payload(document: Any | None = None) -> dict[str, Any]:
    project = build_release_1_0_project()[0] if document is None else get_geoproject_document(document)
    validation = validate_geoproject_model(project, require_mesh=project.mesh_model.mesh_document is not None, require_results=bool(project.result_store.phase_results))
    compiler = compile_phase_solver_inputs(project, block_on_errors=False) if project.mesh_model.mesh_document is not None else None
    solver_payload = dict(project.solver_model.metadata.get("last_incremental_solve", {}) or {})
    acceptance = audit_release_1_0(project, solver_summary=solver_payload) if project.result_store.phase_results else None
    mesh = project.mesh_model.mesh_document
    phases = project.phases_in_order()
    return {
        "contract": "release_1_0_showcase_panel_v1",
        "title": "GeoAI SimKit 1.0 Basic - accepted staged foundation pit",
        "release": project.metadata.get("release", project.project_settings.metadata.get("release", "1.0.0-basic")),
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
        "mesh": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types)), "metadata": dict(mesh.metadata)},
        "readiness": validation.readiness,
        "validation": validation.to_dict(),
        "compiler": None if compiler is None else compiler.to_dict(),
        "acceptance": None if acceptance is None else acceptance.to_dict(),
        "actions": ["build_release_1_0_project", "run_release_1_0_workflow", "export_release_1_0_bundle"],
    }


def create_release_1_0_showcase_project(document: Any | None = None) -> dict[str, Any]:
    project, mesh_report = build_release_1_0_project()
    if document is not None:
        try:
            target = get_geoproject_document(document)
            for field_name in target.__dataclass_fields__:
                setattr(target, field_name, getattr(project, field_name))
            mark_geoproject_dirty(document, target)
        except Exception:
            pass
    return {"ok": True, "project": project, "mesh_report": mesh_report, "payload": build_release_1_0_showcase_payload(project)}


def run_release_1_0_showcase(document: Any | None = None, *, output_dir: str | Path | None = None) -> dict[str, Any]:
    if document is None:
        return run_release_1_0_workflow(output_dir=output_dir)
    project = get_geoproject_document(document)
    if not project.geometry_model.volumes:
        project = build_release_1_0_project()[0]
    validation = validate_geoproject_model(project, require_mesh=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=True)
    solver = run_geoproject_incremental_solve(project, compile_if_needed=False, write_results=True)
    acceptance = audit_release_1_0(project, solver_summary=solver)
    artifacts = export_release_1_0_bundle(project, output_dir, validation=validation.to_dict(), compiler=compiler.to_dict(), solver_summary=solver.to_dict(), acceptance=acceptance.to_dict()) if output_dir is not None else None
    mark_geoproject_dirty(document, project)
    return {
        "contract": "release_1_0_showcase_run_v1",
        "ok": bool(acceptance.accepted),
        "validation": validation.to_dict(),
        "compiler": compiler.to_dict(),
        "solver_summary": solver.to_dict(),
        "acceptance": acceptance.to_dict(),
        "artifacts": None if artifacts is None else artifacts.to_dict(),
        "payload": build_release_1_0_showcase_payload(project),
    }


__all__ = ["build_release_1_0_showcase_payload", "create_release_1_0_showcase_project", "run_release_1_0_showcase"]
