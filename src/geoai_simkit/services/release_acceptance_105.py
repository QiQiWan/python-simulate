from __future__ import annotations

"""Release 1.0.5 acceptance audit.

1.0.5 builds on the 1.0 Basic acceptance gate and adds explicit checks for GUI
contract hardening, Gmsh/OCC meshing route metadata, K0 initialization,
staged Mohr-Coulomb controls, bundle/report completeness and tutorial presence.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.gui_desktop_hardening import audit_phase_workbench_desktop_contract
from geoai_simkit.services.release_acceptance import audit_release_1_0


@dataclass(slots=True)
class Release105AcceptanceFinding:
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
class Release105AcceptanceReport:
    contract: str = "geoai_simkit_release_1_0_5_acceptance_v1"
    status: str = "unknown"
    accepted: bool = False
    findings: list[Release105AcceptanceFinding] = field(default_factory=list)
    release_1_0: dict[str, Any] = field(default_factory=dict)
    gui: dict[str, Any] = field(default_factory=dict)
    mesh_route: dict[str, Any] = field(default_factory=dict)
    k0: dict[str, Any] = field(default_factory=dict)
    mohr_coulomb: dict[str, Any] = field(default_factory=dict)
    solver_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(Release105AcceptanceFinding(str(severity), str(code), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [item.to_dict() for item in self.findings],
            "release_1_0": dict(self.release_1_0),
            "gui": dict(self.gui),
            "mesh_route": dict(self.mesh_route),
            "k0": dict(self.k0),
            "mohr_coulomb": dict(self.mohr_coulomb),
            "solver_summary": dict(self.solver_summary),
            "metadata": dict(self.metadata),
        }


def _dict_from(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def audit_release_1_0_5(
    project: Any,
    *,
    solver_summary: Any | None = None,
    tutorial_path: str | Path | None = None,
) -> Release105AcceptanceReport:
    solver_payload = _dict_from(solver_summary) or dict(getattr(project.solver_model, "metadata", {}).get("last_incremental_solve", {}) or {})
    base = audit_release_1_0(project, solver_summary=solver_payload)
    gui = audit_phase_workbench_desktop_contract()
    mesh_route = dict(getattr(project.mesh_model, "metadata", {}).get("last_gmsh_occ_mesh_route", {}) or {})
    k0 = dict(getattr(project.solver_model, "metadata", {}).get("k0_initial_stress", {}) or {})
    mc = dict(getattr(project.solver_model, "metadata", {}).get("staged_mohr_coulomb_control", {}) or {})
    report = Release105AcceptanceReport(
        release_1_0=base.to_dict(),
        gui=gui.to_dict(),
        mesh_route=mesh_route,
        k0=k0,
        mohr_coulomb=mc,
        solver_summary=solver_payload,
        metadata={"release": getattr(project, "metadata", {}).get("release", "")},
    )
    for finding in base.findings:
        severity = "blocker" if finding.severity == "blocker" else finding.severity
        report.add(severity, f"1_0.{finding.code}", finding.message, finding.recommendation, **finding.metadata)
    for finding in gui.findings:
        # Missing optional GUI packages are not blockers for headless CI acceptance,
        # but route/phase contract problems remain blockers.
        severity = finding.severity
        if finding.code in {"gui.qt.optional_missing", "gui.pyvista.optional_missing"}:
            severity = "warning"
        report.add(severity, finding.code, finding.message, finding.recommendation, **finding.metadata)
    if not base.accepted:
        report.add("blocker", "release_1_0.base_not_accepted", "The underlying 1.0 Basic acceptance gate did not pass.")
    if not gui.ok:
        report.add("blocker", "gui.contract_not_ready", "The phase workbench GUI contract has blocker findings.")
    if not mesh_route:
        report.add("blocker", "mesh.route.missing", "No Gmsh/OCC preferred meshing route metadata was recorded.", "Run generate_gmsh_occ_or_shared_hex8_mesh before acceptance.")
    elif not mesh_route.get("ok", False):
        report.add("blocker", "mesh.route.failed", "The selected production mesh route failed.")
    elif mesh_route.get("fallback_used", False):
        report.add("warning", "mesh.route.fallback_used", "Gmsh/OCC route fell back to shared-node Hex8 production mesh.", "Install and validate Gmsh/OCC for tetrahedral production meshing.", reason=mesh_route.get("fallback_reason", ""))
    if not k0 or not list(k0.get("states", []) or []):
        report.add("blocker", "k0.missing", "K0 initial stress states are missing.", "Run apply_k0_initial_stress.")
    if not mc or not list(mc.get("material_ids", []) or []):
        report.add("blocker", "mc.control.missing", "Staged Mohr-Coulomb control block is missing.", "Run configure_staged_mohr_coulomb_controls.")
    if solver_payload and not solver_payload.get("accepted", False):
        report.add("blocker", "solver.not_accepted", "The incremental staged solve was not accepted.")
    if tutorial_path is not None and not Path(tutorial_path).exists():
        report.add("warning", "docs.tutorial.missing", "The 1.0.5 tutorial path does not exist.", path=str(tutorial_path))
    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_0_5_basic" if report.accepted else "blocked_1_0_5_basic"
    return report


__all__ = ["Release105AcceptanceFinding", "Release105AcceptanceReport", "audit_release_1_0_5"]
