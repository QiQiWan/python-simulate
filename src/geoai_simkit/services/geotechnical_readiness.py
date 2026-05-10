from __future__ import annotations

"""Headless production-readiness service for 3D geotechnical analysis."""

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
from geoai_simkit.modules import meshing


def build_geotechnical_readiness_report(project: Any) -> dict[str, Any]:
    """Aggregate strict Project Port v2 summaries and module readiness gates."""

    context = as_project_context(project)
    report: dict[str, Any] = {
        "solid_mesh": solid_mesh_summary(context).to_dict(),
        "material_mapping": material_mapping_summary(context).to_dict(),
        "boundary_conditions": boundary_condition_summary(context).to_dict(),
        "loads": load_summary(context).to_dict(),
        "interfaces": interface_summary(context).to_dict(),
        "stage_activation": stage_activation_summary(context).to_dict(),
        "analysis_readiness": analysis_readiness_summary(context).to_dict(),
    }
    try:
        report["solid_analysis_gate"] = meshing.validate_solid_analysis_readiness(context).to_dict()
    except Exception as exc:  # pragma: no cover - defensive, service should remain UI-safe
        report["solid_analysis_gate"] = {"ready": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        report["region_material_audit"] = meshing.audit_region_material_mapping(context)
    except Exception as exc:  # pragma: no cover
        report["region_material_audit"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        report["interface_contact_gate"] = meshing.validate_interface_contact_readiness(context)
    except Exception as exc:  # pragma: no cover
        report["interface_contact_gate"] = {"ready": False, "error": f"{type(exc).__name__}: {exc}"}
    blocking = list(report["analysis_readiness"].get("blocking_issues", []))
    gate = report.get("solid_analysis_gate", {})
    if isinstance(gate, dict):
        for row in gate.get("blocking_issues", []) or []:
            code = row.get("code") if isinstance(row, dict) else str(row)
            if code and code not in blocking:
                blocking.append(str(code))
    report["ready"] = not blocking
    report["blocking_issues"] = blocking
    report["contract"] = "geotechnical_readiness_v2"
    return report


__all__ = ["build_geotechnical_readiness_report"]
