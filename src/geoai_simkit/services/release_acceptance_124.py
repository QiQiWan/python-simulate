from __future__ import annotations

"""Release 1.2.4 acceptance audit."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.gui_interaction_recording import record_phase_workbench_interaction_contract
from geoai_simkit.services.release_acceptance_113 import audit_release_1_1_3


@dataclass(slots=True)
class Release124Finding:
    severity: str
    code: str
    message: str
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message, "recommendation": self.recommendation, "metadata": dict(self.metadata)}


@dataclass(slots=True)
class Release124AcceptanceReport:
    contract: str = "geoai_simkit_release_1_2_4_acceptance_v1"
    status: str = "unknown"
    accepted: bool = False
    findings: list[Release124Finding] = field(default_factory=list)
    release_1_1_3: dict[str, Any] = field(default_factory=dict)
    global_newton: dict[str, Any] = field(default_factory=dict)
    native_gmsh_exchange: dict[str, Any] = field(default_factory=dict)
    consolidation: dict[str, Any] = field(default_factory=dict)
    interface_iteration: dict[str, Any] = field(default_factory=dict)
    gui_recording: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for row in self.findings if row.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for row in self.findings if row.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(Release124Finding(str(severity), str(code), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [row.to_dict() for row in self.findings],
            "release_1_1_3": dict(self.release_1_1_3),
            "global_newton": dict(self.global_newton),
            "native_gmsh_exchange": dict(self.native_gmsh_exchange),
            "consolidation": dict(self.consolidation),
            "interface_iteration": dict(self.interface_iteration),
            "gui_recording": dict(self.gui_recording),
            "metadata": dict(self.metadata),
        }


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def audit_release_1_2_4(
    project: Any,
    *,
    newton_summary: Any | None = None,
    tutorial_path: str | Path | None = None,
) -> Release124AcceptanceReport:
    newton = _payload(newton_summary) or dict(project.solver_model.metadata.get("last_global_mohr_coulomb_newton_solve", {}) or {})
    base = audit_release_1_1_3(project, solver_summary=dict(project.solver_model.metadata.get("last_staged_mohr_coulomb_solve", {}) or {}), tutorial_path=tutorial_path)
    native_exchange = dict(project.mesh_model.metadata.get("last_gmsh_occ_native_exchange", {}) or {})
    consolidation = dict(project.solver_model.metadata.get("consolidation_coupling_state", {}) or {})
    interface_iteration = dict(project.solver_model.metadata.get("interface_contact_iteration", {}) or {})
    gui_recording = record_phase_workbench_interaction_contract().to_dict()
    report = Release124AcceptanceReport(
        release_1_1_3=base.to_dict(),
        global_newton=newton,
        native_gmsh_exchange=native_exchange,
        consolidation=consolidation,
        interface_iteration=interface_iteration,
        gui_recording=gui_recording,
        metadata={"release": project.metadata.get("release", "")},
    )
    for finding in base.findings:
        severity = finding.severity
        if finding.code in {"mesh.gmsh_occ_project_fallback", "1_0_5.mesh.route.fallback_used"}:
            severity = "warning"
        report.add(severity, f"1_1_3.{finding.code}", finding.message, finding.recommendation, **finding.metadata)
    if not base.accepted:
        report.add("blocker", "base_1_1_3.not_accepted", "Underlying 1.1.3 acceptance did not pass.")
    if not newton:
        report.add("blocker", "newton.missing", "Global Newton-Raphson Mohr-Coulomb summary is missing.")
    elif not newton.get("accepted", False):
        report.add("blocker", "newton.not_accepted", "Global Newton-Raphson Mohr-Coulomb solve was not accepted.")
    elif not newton.get("consistent_tangent", False):
        report.add("blocker", "newton.no_consistent_tangent", "Consistent tangent flag was not set.")
    if not native_exchange:
        report.add("blocker", "gmsh_native_exchange.missing", "Native Gmsh/OCC physical group exchange metadata is missing.")
    elif not native_exchange.get("ok", False):
        report.add("blocker", "gmsh_native_exchange.not_ok", "Gmsh/OCC physical group exchange did not report ok.")
    elif native_exchange.get("fallback_used", False):
        report.add("warning", "gmsh_native_exchange.fallback", "Native gmsh runtime was not available; physical-group manifest surrogate was used.", "Install gmsh to enable native .msh exchange.")
    if not consolidation:
        report.add("blocker", "consolidation.missing", "Consolidation coupling state is missing.")
    elif not consolidation.get("ok", False):
        report.add("blocker", "consolidation.not_ok", "Consolidation coupling did not report ok.")
    if not interface_iteration:
        report.add("blocker", "interface_iteration.missing", "Interface open/close iteration state is missing.")
    elif not interface_iteration.get("ok", False):
        report.add("blocker", "interface_iteration.not_ok", "Interface open/close iteration did not report ok.")
    if not gui_recording.get("ok", False):
        report.add("blocker", "gui_recording.not_ok", "Six-phase GUI interaction recording contract is not ready.")
    if not gui_recording.get("old_gui_blocked", False):
        report.add("blocker", "gui_launcher.legacy_default", "Old flat GUI is still the default launcher.")
    if tutorial_path is not None and not Path(tutorial_path).exists():
        report.add("warning", "docs.tutorial_missing", "1.2.4 tutorial artifact was requested but not found.")
    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_2_4_basic" if report.accepted else "blocked_1_2_4_basic"
    return report


__all__ = ["Release124Finding", "Release124AcceptanceReport", "audit_release_1_2_4"]
