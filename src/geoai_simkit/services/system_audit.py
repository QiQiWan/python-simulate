from __future__ import annotations

"""0.9 Alpha workflow audit helpers."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.model_validation import validate_geoproject_model


@dataclass(slots=True)
class AuditFinding:
    severity: str
    area: str
    message: str
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "area": self.area,
            "message": self.message,
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class SystemAuditReport:
    contract: str = "geoproject_alpha_system_audit_v1"
    status: str = "unknown"
    findings: list[AuditFinding] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    scorecard: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "blocker")

    @property
    def risk_count(self) -> int:
        return sum(1 for item in self.findings if item.severity in {"risk", "warning"})

    def add(self, severity: str, area: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(AuditFinding(str(severity), str(area), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "blocker_count": self.blocker_count,
            "risk_count": self.risk_count,
            "findings": [item.to_dict() for item in self.findings],
            "validation": dict(self.validation),
            "scorecard": dict(self.scorecard),
            "metadata": dict(self.metadata),
        }


def audit_geoproject_alpha(project: Any) -> SystemAuditReport:
    """Audit the 0.9 Alpha closed-loop model and return an actionable report."""

    validation = validate_geoproject_model(project, require_mesh=True, require_results=True)
    report = SystemAuditReport(validation=validation.to_dict())
    mesh = getattr(project.mesh_model, "mesh_document", None)
    compiled = dict(getattr(project.solver_model, "compiled_phase_models", {}) or {})
    results = dict(getattr(project.result_store, "phase_results", {}) or {})
    phases = project.phase_ids() if hasattr(project, "phase_ids") else []

    if not validation.ok:
        report.add("blocker", "validation", "Model validation has errors.", "Fix validation errors before treating the model as engineering-ready.", error_count=validation.error_count)
    if mesh is None or int(getattr(mesh, "cell_count", 0)) <= 0:
        report.add("blocker", "mesh", "No usable 3D mesh is attached.", "Generate a solid mesh in the mesh phase before solving.")
    if len(compiled) != len(phases):
        report.add("risk", "solver", "Compiled phase count does not match phase count.", "Re-run phase compilation after any geometry, mesh, material or phase edit.", compiled=len(compiled), phases=len(phases))
    if len(results) != len(phases):
        report.add("risk", "results", "Result phase count does not match phase count.", "Run the incremental solver or preview solver for all phases.", results=len(results), phases=len(phases))
    if mesh is not None:
        cell_types = {str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])}
        if any("preview" in item for item in cell_types):
            report.add("warning", "mesh", "The current mesh uses preview element types.", "Use production Gmsh/OCC or validated STL volume meshing for certification-grade studies.", cell_types=sorted(cell_types))
    solve_summary = dict(getattr(project.solver_model, "metadata", {}).get("last_incremental_solve", {}) or {})
    if not solve_summary:
        report.add("risk", "solver", "No incremental solver summary is recorded.", "Run run_geoproject_incremental_solve before releasing the case.")
    nonconverged = []
    for row in compiled.values():
        block = dict(getattr(row, "metadata", {}).get("IncrementalSolveBlock", {}) or {})
        if block and not bool(block.get("converged", False)):
            nonconverged.append(str(block.get("phase_id", getattr(row, "phase_id", ""))))
    if nonconverged:
        report.add("risk", "solver", "One or more phases did not satisfy residual convergence tolerance.", "Treat results as diagnostic until boundary conditions, materials and mesh are improved.", phase_ids=nonconverged)

    report.scorecard = {
        "geometry_ready": validation.readiness.get("geometry_ready", False),
        "semantic_ready": validation.readiness.get("semantic_ready", False),
        "mesh_ready": validation.readiness.get("mesh_ready", False),
        "phase_compiled": len(compiled) == len(phases) and bool(phases),
        "results_available": len(results) == len(phases) and bool(phases),
        "warnings": validation.warning_count,
        "errors": validation.error_count,
    }
    report.status = "blocked" if report.blocker_count else ("alpha_ready_with_risks" if report.risk_count else "alpha_ready")
    return report


__all__ = ["AuditFinding", "SystemAuditReport", "audit_geoproject_alpha"]
