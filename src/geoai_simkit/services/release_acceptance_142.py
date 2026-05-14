from __future__ import annotations

"""Acceptance gate for 1.4.2a CAD facade hardening.

This release deliberately does **not** claim full Native CAD/OCC integration.
It accepts the hardened facade only when fallback/native backend state is
explicitly reported, CAD feature execution is auditable, and the synthetic
persistent-topology index is present. A later native-BRep release must use a
separate acceptance gate.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.services.cad_facade_kernel import build_cad_topology_index, probe_cad_facade_kernel


@dataclass(slots=True)
class Release142AcceptanceReport:
    contract: str = "geoai_simkit_release_1_4_2a_cad_facade_acceptance_v1"
    status: str = "rejected"
    accepted: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "status": self.status,
            "accepted": bool(self.accepted),
            "blocker_count": int(self.blocker_count),
            "warning_count": int(self.warning_count),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _backend_mode(cad_report: dict[str, Any]) -> str:
    metadata = dict(cad_report.get("metadata", {}) or {})
    if metadata.get("backend_mode"):
        return str(metadata["backend_mode"])
    if cad_report.get("native_backend_used") and not cad_report.get("fallback_used"):
        return "native_passthrough_facade"
    if cad_report.get("native_backend_used") and cad_report.get("fallback_used"):
        return "mixed_facade"
    return "deterministic_aabb_facade"


def audit_release_1_4_2(project: Any) -> Release142AcceptanceReport:
    blockers: list[str] = []
    warnings: list[str] = []
    capability = probe_cad_facade_kernel()
    topology = build_cad_topology_index(project, attach=True)
    cad_report = dict(getattr(project.geometry_model, "metadata", {}).get("last_cad_occ_feature_execution", {}) or {})

    if __version__ not in {"1.4.2a-cad-facade", "1.4.2c-native-roundtrip", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}:
        blockers.append(f"Unexpected version: {__version__}")
    if not topology.ok or topology.solid_count <= 0:
        blockers.append("CAD facade topology index has no solid records.")
    if topology.to_dict().get("contract") != "geoai_simkit_cad_facade_topology_index_v1":
        blockers.append("CAD topology index uses an outdated/native claim contract name.")
    if not cad_report:
        blockers.append("No CAD facade feature execution report was attached to the project.")
    elif not cad_report.get("ok"):
        blockers.append("CAD facade feature execution report is not ok.")
    else:
        if cad_report.get("contract") != "geoai_simkit_cad_facade_feature_execution_v1":
            blockers.append("CAD feature execution report uses an outdated/native claim contract name.")
        if "fallback_used" not in cad_report or "native_backend_used" not in cad_report:
            blockers.append("CAD facade report must explicitly state native_backend_used and fallback_used.")
        if cad_report.get("fallback_used") and cad_report.get("backend") not in {"aabb_fallback", "mixed"}:
            blockers.append("Fallback execution must be explicitly labelled as aabb_fallback or mixed.")
        metadata = dict(cad_report.get("metadata", {}) or {})
        if metadata.get("native_brep_certified") is not False:
            blockers.append("1.4.2a facade reports must explicitly set native_brep_certified=false.")

    backend_mode = _backend_mode(cad_report)
    if not capability.native_available:
        warnings.append("Native OCC backend is not available; deterministic AABB facade fallback is active.")
    if cad_report.get("fallback_used"):
        warnings.append("CAD facade feature execution used deterministic AABB fallback; this is accepted for 1.4.2a but not certified native CAD output.")
    if cad_report.get("native_backend_used"):
        warnings.append("Native-like gmsh/OCC backend was used through the facade; native BRep topology is still not certified in 1.4.2a.")

    accepted = not blockers
    return Release142AcceptanceReport(
        status="accepted_1_4_2a_cad_facade" if accepted else "rejected_1_4_2a_cad_facade",
        accepted=accepted,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        blockers=blockers,
        warnings=warnings,
        metadata={
            "release": __version__,
            "release_mode": "cad_facade_hardening",
            "native_cad_claimed": False,
            "native_brep_certified": False,
            "backend_mode": backend_mode,
            "capability": capability.to_dict(),
            "topology": topology.to_dict(),
            "cad_feature_execution": cad_report,
            "gui_cad_facade": {
                "visible_backend_status_required": True,
                "persistent_naming": True,
                "fallback_state_explicit": True,
            },
        },
    )


__all__ = ["Release142AcceptanceReport", "audit_release_1_4_2"]
