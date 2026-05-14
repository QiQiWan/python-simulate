from __future__ import annotations

"""Acceptance gate for 1.4.2c native gmsh/OCC boolean mesh roundtrip."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.services.gmsh_occ_boolean_roundtrip import probe_gmsh_occ_boolean_roundtrip


@dataclass(slots=True)
class Release142cAcceptanceReport:
    contract: str = "geoai_simkit_release_1_4_2c_native_roundtrip_acceptance_v1"
    status: str = "rejected"
    accepted: bool = False
    native_certified: bool = False
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
            "native_certified": bool(self.native_certified),
            "blocker_count": int(self.blocker_count),
            "warning_count": int(self.warning_count),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def audit_release_1_4_2c(project: Any, *, require_native_certified: bool = False) -> Release142cAcceptanceReport:
    blockers: list[str] = []
    warnings: list[str] = []
    capability = probe_gmsh_occ_boolean_roundtrip().to_dict()
    roundtrip = dict(getattr(getattr(project, "mesh_model", None), "metadata", {}).get("last_gmsh_occ_boolean_mesh_roundtrip", {}) or {})
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if __version__ not in {"1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}:
        blockers.append(f"Unexpected version: {__version__}")
    if not roundtrip:
        blockers.append("No 1.4.2c gmsh/OCC boolean mesh roundtrip report was attached.")
    elif roundtrip.get("contract") != "geoai_simkit_gmsh_occ_boolean_mesh_roundtrip_v1":
        blockers.append("Roundtrip report uses an unexpected contract name.")
    elif not roundtrip.get("ok"):
        blockers.append("Roundtrip report is not ok.")
    if mesh is None:
        blockers.append("Project has no mesh document after roundtrip.")
    else:
        if mesh.node_count <= 0 or mesh.cell_count <= 0:
            blockers.append("Roundtrip mesh has no nodes or cells.")
        cell_types = set(str(v).lower() for v in list(getattr(mesh, "cell_types", []) or []))
        if "tet4" not in cell_types:
            blockers.append("Roundtrip mesh must include tet4 cells.")
        physical = list(getattr(mesh, "cell_tags", {}).get("physical_volume", []) or [])
        if len(physical) != mesh.cell_count:
            blockers.append("Every mesh cell must carry a physical_volume tag.")
        material = list(getattr(mesh, "cell_tags", {}).get("material_id", []) or [])
        if len(material) != mesh.cell_count:
            blockers.append("Every mesh cell must carry a material_id tag, even if empty.")
    native = bool(roundtrip.get("native_backend_used")) and not bool(roundtrip.get("fallback_used"))
    if require_native_certified and not native:
        blockers.append("Native-certified 1.4.2c acceptance requires native_backend_used=true and fallback_used=false.")
    if not native:
        warnings.append("1.4.2c native gmsh/OCC roundtrip did not execute in this environment; only the physical-group roundtrip contract is accepted.")
    else:
        warnings.append("Native gmsh/OCC boolean mesh roundtrip executed; validate generated .msh artifacts in the target desktop environment.")
    physical_group_count = int(roundtrip.get("physical_group_count", 0) or 0)
    imported_group_count = int(roundtrip.get("imported_group_count", 0) or 0)
    if physical_group_count <= 0 or imported_group_count <= 0:
        blockers.append("Physical group roundtrip did not produce/import physical groups.")
    accepted = not blockers
    status = "accepted_1_4_2c_native_roundtrip" if accepted and native else ("accepted_1_4_2c_roundtrip_contract" if accepted else "rejected_1_4_2c_roundtrip")
    return Release142cAcceptanceReport(
        status=status,
        accepted=accepted,
        native_certified=bool(native),
        blocker_count=len(blockers),
        warning_count=len(warnings) + len(roundtrip.get("warnings", []) or []),
        blockers=blockers,
        warnings=warnings + list(roundtrip.get("warnings", []) or []),
        metadata={
            "release": __version__,
            "require_native_certified": bool(require_native_certified),
            "capability": capability,
            "roundtrip": roundtrip,
            "mesh_summary": None if mesh is None else {"node_count": mesh.node_count, "cell_count": mesh.cell_count, "cell_types": sorted(set(mesh.cell_types))},
        },
    )


__all__ = ["Release142cAcceptanceReport", "audit_release_1_4_2c"]
