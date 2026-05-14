from __future__ import annotations

"""Release 1.4.5 native geometry certification acceptance gate."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.geoproject.cad_shape_store import CadShapeStore
from geoai_simkit.services.native_runtime_verification import verify_native_desktop_runtime
from geoai_simkit.services.boolean_topology_lineage import validate_boolean_topology_lineage
from geoai_simkit.services.topology_material_phase_binding import validate_topology_material_phase_bindings

@dataclass(slots=True)
class Release145AcceptanceReport:
    contract: str = "geoai_simkit_release_1_4_5_native_geometry_certification_acceptance_v1"
    accepted: bool = False
    status: str = "not_run"
    native_brep_certified: bool = False
    runtime_verified: bool = False
    ifc_representation_expanded: bool = False
    topology_lineage_valid: bool = False
    topology_binding_valid: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"contract":self.contract,"accepted":bool(self.accepted),"status":self.status,"native_brep_certified":bool(self.native_brep_certified),"runtime_verified":bool(self.runtime_verified),"ifc_representation_expanded":bool(self.ifc_representation_expanded),"topology_lineage_valid":bool(self.topology_lineage_valid),"topology_binding_valid":bool(self.topology_binding_valid),"blocker_count":self.blocker_count,"warning_count":self.warning_count,"blockers":list(self.blockers),"warnings":list(self.warnings),"metadata":dict(self.metadata)}


def audit_release_1_4_5(project: Any, *, require_native_brep: bool = False, require_lineage: bool = True) -> Release145AcceptanceReport:
    blockers: list[str] = []
    warnings: list[str] = []
    if __version__ not in {"1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}:
        blockers.append(f"Version must be 1.4.5-native-geometry-certification or later 1.4.6 CAD stabilization, got {__version__}.")
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        blockers.append("CadShapeStore is missing.")
        store_summary = {}
    else:
        store_summary = store.summary()
    native_count = int(store_summary.get("native_brep_certified_count", 0) or 0)
    native_certified = native_count > 0
    if require_native_brep and not native_certified:
        blockers.append("Native BRep-certified imported shape is required but none exists.")
    runtime = verify_native_desktop_runtime(require_native_brep=False)
    if not runtime.ok:
        warnings.extend(runtime.blockers)
    if not runtime.native_brep_certification_possible:
        warnings.append("Desktop runtime cannot currently certify native BRep; surrogate/reference mode remains active.")
    ifc_report = project.metadata.get("release_1_4_5_ifc_representation_expansion", {}) if hasattr(project, "metadata") else {}
    ifc_expanded = bool(ifc_report.get("ok"))
    if not ifc_expanded:
        warnings.append("No IFC representation expansion report is attached to the project.")
    lineage_validation = validate_boolean_topology_lineage(project, require_face_lineage=False)
    lineage_ok = bool(lineage_validation.get("ok"))
    if require_lineage and not lineage_ok:
        blockers.append("Boolean/import topology lineage validation failed or lineage is missing.")
    binding_validation = validate_topology_material_phase_bindings(project, require_face_bindings=True, require_phase_bindings=True)
    binding_ok = bool(binding_validation.get("ok"))
    if not binding_ok:
        blockers.append("Face/edge/material/phase topology binding validation failed.")
    accepted = not blockers
    status = "accepted_1_4_5_native_brep_certified" if accepted and native_certified else ("accepted_1_4_5_native_geometry_certification_contract" if accepted else "rejected_1_4_5_native_geometry_certification")
    return Release145AcceptanceReport(
        accepted=accepted,
        status=status,
        native_brep_certified=native_certified,
        runtime_verified=runtime.ok,
        ifc_representation_expanded=ifc_expanded,
        topology_lineage_valid=lineage_ok,
        topology_binding_valid=binding_ok,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        blockers=blockers,
        warnings=warnings,
        metadata={"runtime":runtime.to_dict(),"cad_shape_store_summary":store_summary,"ifc_representation_expansion":ifc_report,"lineage_validation":lineage_validation,"binding_validation":binding_validation},
    )

__all__ = ["Release145AcceptanceReport", "audit_release_1_4_5"]
