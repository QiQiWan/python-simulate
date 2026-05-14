from __future__ import annotations

"""Release 1.1.3 acceptance audit.

1.1.3 builds on 1.0.5 and checks the four deeper hardening lines:
nonlinear Mohr-Coulomb result state, Gmsh/OCC Tet4 project-mesh contract, GUI
interaction hardening, and groundwater/contact interface state.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.gui_interaction_hardening import audit_gui_interaction_hardening
from geoai_simkit.services.release_acceptance_105 import audit_release_1_0_5


@dataclass(slots=True)
class Release113Finding:
    severity: str
    code: str
    message: str
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message, "recommendation": self.recommendation, "metadata": dict(self.metadata)}


@dataclass(slots=True)
class Release113AcceptanceReport:
    contract: str = "geoai_simkit_release_1_1_3_acceptance_v1"
    status: str = "unknown"
    accepted: bool = False
    findings: list[Release113Finding] = field(default_factory=list)
    release_1_0_5: dict[str, Any] = field(default_factory=dict)
    gui_interaction: dict[str, Any] = field(default_factory=dict)
    gmsh_occ_project_mesh: dict[str, Any] = field(default_factory=dict)
    mohr_coulomb_solve: dict[str, Any] = field(default_factory=dict)
    hydro: dict[str, Any] = field(default_factory=dict)
    contact: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocker_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity in {"warning", "risk"})

    def add(self, severity: str, code: str, message: str, recommendation: str = "", **metadata: Any) -> None:
        self.findings.append(Release113Finding(str(severity), str(code), str(message), str(recommendation), dict(metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [row.to_dict() for row in self.findings],
            "release_1_0_5": dict(self.release_1_0_5),
            "gui_interaction": dict(self.gui_interaction),
            "gmsh_occ_project_mesh": dict(self.gmsh_occ_project_mesh),
            "mohr_coulomb_solve": dict(self.mohr_coulomb_solve),
            "hydro": dict(self.hydro),
            "contact": dict(self.contact),
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


def audit_release_1_1_3(
    project: Any,
    *,
    solver_summary: Any | None = None,
    tutorial_path: str | Path | None = None,
) -> Release113AcceptanceReport:
    solver_payload = _payload(solver_summary) or dict(getattr(project.solver_model, "metadata", {}).get("last_staged_mohr_coulomb_solve", {}) or {})
    base = audit_release_1_0_5(project, solver_summary=dict(getattr(project.solver_model, "metadata", {}).get("last_incremental_solve", {}) or {}), tutorial_path=tutorial_path)
    gui = audit_gui_interaction_hardening()
    mesh_route = dict(getattr(project.mesh_model, "metadata", {}).get("last_gmsh_occ_project_mesh", {}) or {})
    hydro = dict(getattr(project.solver_model, "metadata", {}).get("hydro_mechanical_state", {}) or {})
    contact = dict(getattr(project.solver_model, "metadata", {}).get("contact_interface_enhancement", {}) or {})
    report = Release113AcceptanceReport(
        release_1_0_5=base.to_dict(),
        gui_interaction=gui.to_dict(),
        gmsh_occ_project_mesh=mesh_route,
        mohr_coulomb_solve=solver_payload,
        hydro=hydro,
        contact=contact,
        metadata={"release": getattr(project, "metadata", {}).get("release", "")},
    )
    for finding in base.findings:
        severity = finding.severity
        if finding.code in {"mesh.route.fallback_used"}:
            severity = "warning"
        report.add(severity, f"1_0_5.{finding.code}", finding.message, finding.recommendation, **finding.metadata)
    if not base.accepted:
        report.add("blocker", "base_1_0_5.not_accepted", "Underlying 1.0.5 acceptance did not pass.")
    if not gui.ok:
        report.add("blocker", "gui.interaction.not_ready", "GUI interaction hardening contract did not pass.")
    if not mesh_route:
        report.add("blocker", "mesh.gmsh_occ_project_missing", "1.1 Gmsh/OCC project mesh route metadata is missing.")
    else:
        if mesh_route.get("contract") != "geoai_simkit_gmsh_occ_project_mesh_v1":
            report.add("blocker", "mesh.gmsh_occ_project_contract", "Unexpected Gmsh/OCC project mesh contract.")
        if not mesh_route.get("ok", False):
            report.add("blocker", "mesh.gmsh_occ_project_not_ok", "Gmsh/OCC project mesh route did not report ok.")
        if mesh_route.get("fallback_used", False):
            report.add("warning", "mesh.gmsh_occ_project_fallback", "Native Gmsh/OCC was not used; deterministic Tet4 surrogate is recorded.", "Install gmsh/OCC runtime for native meshing.", fallback_reason=mesh_route.get("fallback_reason", ""))
    mesh = getattr(project.mesh_model, "mesh_document", None)
    if mesh is None:
        report.add("blocker", "mesh.missing", "Mesh document is missing.")
    elif not all(str(t).lower() == "tet4" for t in list(mesh.cell_types or [])):
        report.add("blocker", "mesh.not_tet4", "1.1.3 requires the project mesh contract to be Tet4.", cell_types=list(mesh.cell_types or []))
    if not solver_payload:
        report.add("blocker", "mc_solve.missing", "Staged Mohr-Coulomb solve summary is missing.")
    elif not solver_payload.get("accepted", False):
        report.add("blocker", "mc_solve.not_accepted", "Staged Mohr-Coulomb solve was not accepted.")
    elif int(solver_payload.get("state_count", 0) or 0) <= 0:
        report.add("blocker", "mc_solve.no_states", "Staged Mohr-Coulomb solve produced no cell states.")
    if not hydro:
        report.add("blocker", "hydro.missing", "Hydro-mechanical pore pressure state is missing.")
    elif int(hydro.get("phase_count", 0) or 0) <= 0:
        report.add("blocker", "hydro.no_phases", "Hydro-mechanical state has no phase records.")
    if not contact:
        report.add("blocker", "contact.missing", "Contact/interface enhancement state is missing.")
    elif int(contact.get("interface_count", 0) or 0) <= 0:
        report.add("blocker", "contact.no_interfaces", "No structural interfaces were materialized.")
    if tutorial_path is not None and not Path(tutorial_path).exists():
        report.add("warning", "docs.tutorial_missing", "1.1.3 tutorial artifact was requested but not found.")
    report.accepted = report.blocker_count == 0
    report.status = "accepted_1_1_3_basic" if report.accepted else "blocked_1_1_3_basic"
    return report


__all__ = ["Release113Finding", "Release113AcceptanceReport", "audit_release_1_1_3"]
