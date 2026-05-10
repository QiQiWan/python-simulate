from __future__ import annotations

from typing import Any


def _count(value: Any) -> int:
    try:
        return len(list(value or []))
    except Exception:
        return 0


def build_plaxis_gap_analysis(parameters: dict[str, Any] | None, *, model_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """High-level gap analysis for PLAXIS-like GUI modeling readiness."""
    params = dict(parameters or {})
    payload = dict(model_payload or {})
    dirty = dict(params.get("geometry_dirty_state", {}) or {})
    mesh_quality = dict(params.get("mesh_quality_report", {}) or {})
    face_sets = list(params.get("solver_face_set_rows", []) or [])
    brep = dict(params.get("brep_document", {}) or {})
    component = dict(params.get("component_parameters", {}) or {})
    binding_report = dict(params.get("binding_transfer_report", {}) or {})
    strata = dict(params.get("stratigraphy", {}) or params.get("stratigraphy_surface_plan", {}) or {})
    rows = [
        {"area": "viewport", "item": "pick-apply-feedback loop", "status": "ok" if params.get("last_selection_apply_feedback") or params.get("last_entity_edit_transaction") else "partial", "action": "Use selection inspector and entity transaction service for source-entity changes."},
        {"area": "geometry", "item": "persistent BRep naming", "status": "ok" if _count(brep.get("persistent_name_rows")) else "partial", "action": "Refresh persistent naming after OCC fragment/remesh."},
        {"area": "components", "item": "retaining wall/support/anchor parameterization", "status": "ok" if component else "partial", "action": "Open component panels and apply parameters before remeshing."},
        {"area": "stratigraphy", "item": "layer surface/volume realization", "status": "ok" if strata.get("contract") in {"stratigraphy_surface_plan_v4", "stratigraphy_surface_plan_v5"} else "partial", "action": "Build stratigraphy OCC boolean plan from interpolated layer surfaces."},
        {"area": "mesh", "item": "solver-ready face sets", "status": "ok" if _count(face_sets) else "missing", "action": "Regenerate mesh to extract FaceSet v2 records."},
        {"area": "mesh", "item": "quality and bad-cell traceability", "status": "ok" if mesh_quality.get("contract") in {"mesh_quality_report_v3", "mesh_quality_report_v4"} else "partial", "action": "Run mesh quality check after remeshing."},
        {"area": "binding", "item": "binding transfer after remesh", "status": "warning" if binding_report.get("invalid_bindings") else "ok", "action": "Review binding-transfer prompt for inherited or invalid bindings."},
        {"area": "state", "item": "remesh/resolve invalidation", "status": "warning" if dirty.get("requires_remesh") else "ok", "action": "Regenerate mesh and solve again after entity edits."},
    ]
    return {
        "contract": "plaxis_like_gap_analysis_v1",
        "rows": rows,
        "summary": {
            "ok_count": sum(1 for row in rows if row["status"] == "ok"),
            "partial_count": sum(1 for row in rows if row["status"] == "partial"),
            "warning_count": sum(1 for row in rows if row["status"] == "warning"),
            "missing_count": sum(1 for row in rows if row["status"] == "missing"),
            "ready_for_plaxis_like_modeling": all(row["status"] in {"ok", "warning"} for row in rows),
        },
        "mesh_editable": False,
        "edit_policy": "edit_entities_then_remesh",
    }


__all__ = ["build_plaxis_gap_analysis"]
