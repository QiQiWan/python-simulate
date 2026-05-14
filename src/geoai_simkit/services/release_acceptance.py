from __future__ import annotations

"""Release 1.0 acceptance audit for baseline engineering workflows."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs


@dataclass(slots=True)
class ReleaseAcceptanceFinding:
    severity: str
    code: str
    message: str
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ReleaseAcceptanceReport:
    contract: str = "geoai_simkit_release_1_0_acceptance_v1"
    status: str = "unknown"
    accepted: bool = False
    findings: list[ReleaseAcceptanceFinding] = field(default_factory=list)
    scorecard: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    compiler: dict[str, Any] = field(default_factory=dict)
    solver_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(ReleaseAcceptanceFinding(str(severity), str(code), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [item.to_dict() for item in self.findings],
            "scorecard": dict(self.scorecard),
            "validation": dict(self.validation),
            "compiler": dict(self.compiler),
            "solver_summary": dict(self.solver_summary),
            "metadata": dict(self.metadata),
        }


def audit_release_1_0(project: Any, *, solver_summary: Any | None = None) -> ReleaseAcceptanceReport:
    """Return the 1.0 acceptance status for a solved GeoProjectDocument."""

    validation = validate_geoproject_model(project, require_mesh=True, require_results=True)
    compiler = compile_phase_solver_inputs(project, block_on_errors=False)
    if solver_summary is None:
        raw_solver = dict(getattr(project.solver_model, "metadata", {}).get("last_incremental_solve", {}) or {})
    elif hasattr(solver_summary, "to_dict"):
        raw_solver = solver_summary.to_dict()
    else:
        raw_solver = dict(solver_summary or {})

    report = ReleaseAcceptanceReport(validation=validation.to_dict(), compiler=compiler.to_dict(), solver_summary=raw_solver)
    mesh = getattr(project.mesh_model, "mesh_document", None)
    phases = project.phase_ids() if hasattr(project, "phase_ids") else []
    results = dict(getattr(project.result_store, "phase_results", {}) or {})
    compiled = dict(getattr(project.solver_model, "compiled_phase_models", {}) or {})

    if not validation.ok:
        report.add("blocker", "validation.errors", "Model validation has blocking errors.", "Resolve validation errors before 1.0 acceptance.", error_count=validation.error_count)
    if mesh is None:
        report.add("blocker", "mesh.missing", "No mesh document is attached.", "Generate a production-ready 3D volume mesh.")
    else:
        cell_types = {str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])}
        if any("preview" in item for item in cell_types):
            report.add("blocker", "mesh.preview_cells", "Preview element types are present in the analysis mesh.", "Promote the model to a production Hex8/Tet4 volume mesh.", cell_types=sorted(cell_types))
        if not bool(dict(getattr(mesh, "metadata", {}) or {}).get("production_ready", False)):
            report.add("blocker", "mesh.not_production_ready", "Mesh metadata does not mark the mesh as production_ready.", "Run the 1.0 production mesh builder or a validated Gmsh/OCC mesher.")
        bad = list(getattr(getattr(mesh, "quality", None), "bad_cell_ids", []) or [])
        if bad:
            report.add("blocker", "mesh.bad_cells", "Mesh quality report contains bad cells.", "Fix bad cells before releasing the workflow.", bad_cell_ids=bad[:50])
    if len(compiled) != len(phases) or not phases:
        report.add("blocker", "solver.compiler_incomplete", "Compiled phase model count does not match phase count.", "Recompile phases after model edits.", compiled=len(compiled), phases=len(phases))
    if len(results) != len(phases) or not results:
        report.add("blocker", "results.incomplete", "Result phase count does not match phase count.", "Run the staged solver for every phase.", results=len(results), phases=len(phases))

    phase_records = list(raw_solver.get("phase_records", []) or [])
    if not raw_solver or not phase_records:
        report.add("blocker", "solver.missing_summary", "No structured incremental solver summary is available.", "Run run_geoproject_incremental_solve and persist the returned summary.")
    else:
        nonconverged = [str(row.get("phase_id", "")) for row in phase_records if not bool(row.get("converged", False))]
        if nonconverged:
            report.add("blocker", "solver.nonconverged_phases", "One or more phases failed convergence.", "Adjust mesh, boundary conditions, load basis or solver settings and rerun.", phase_ids=nonconverged)
        if not bool(raw_solver.get("accepted", False)):
            report.add("blocker", "solver.not_accepted", "Incremental solver summary is not accepted.", "All phase records must satisfy the release convergence criterion.")

    report.scorecard = {
        "geometry_ready": validation.readiness.get("geometry_ready", False),
        "semantic_ready": validation.readiness.get("semantic_ready", False),
        "mesh_ready": validation.readiness.get("mesh_ready", False),
        "production_mesh": mesh is not None and bool(dict(getattr(mesh, "metadata", {}) or {}).get("production_ready", False)) and not any("preview" in str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])),
        "phase_compiled": len(compiled) == len(phases) and bool(phases),
        "solver_accepted": bool(raw_solver.get("accepted", False)) if raw_solver else False,
        "results_complete": len(results) == len(phases) and bool(phases),
        "error_count": validation.error_count,
        "warning_count": validation.warning_count,
    }
    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_0_basic" if report.accepted else "blocked"
    return report


__all__ = ["ReleaseAcceptanceFinding", "ReleaseAcceptanceReport", "audit_release_1_0"]
