from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from geoai_simkit._version import __version__
from geoai_simkit.services.step_ifc_shape_import import validate_step_ifc_shape_bindings
from geoai_simkit.services.topology_material_phase_binding import validate_topology_material_phase_bindings
from geoai_simkit.services.native_brep_serialization import probe_native_brep_capability


@dataclass(slots=True)
class Release144AcceptanceReport:
    contract: str = "geoai_simkit_release_1_4_4_topology_binding_acceptance_v1"
    status: str = "rejected_1_4_4_topology_binding"
    accepted: bool = False
    native_brep_certified: bool = False
    native_import_acceptance: bool = False
    imported_shape_count: int = 0
    topology_binding_count: int = 0
    face_binding_count: int = 0
    edge_binding_count: int = 0
    material_binding_count: int = 0
    phase_binding_count: int = 0
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
            "native_brep_certified": bool(self.native_brep_certified),
            "native_import_acceptance": bool(self.native_import_acceptance),
            "imported_shape_count": self.imported_shape_count,
            "topology_binding_count": self.topology_binding_count,
            "face_binding_count": self.face_binding_count,
            "edge_binding_count": self.edge_binding_count,
            "material_binding_count": self.material_binding_count,
            "phase_binding_count": self.phase_binding_count,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def audit_release_1_4_4(project: Any, *, require_native_brep: bool = False, require_face_phase_material_bindings: bool = True) -> Release144AcceptanceReport:
    blockers: list[str] = []
    warnings: list[str] = []
    if __version__ not in {"1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}:
        blockers.append(f"Unexpected version: {__version__}")
    step_validation = validate_step_ifc_shape_bindings(project)
    if not step_validation.get("ok"):
        blockers.extend(str(x) for x in step_validation.get("blockers", []))
    warnings.extend(str(x) for x in step_validation.get("warnings", []))
    binding_validation = validate_topology_material_phase_bindings(project, require_face_bindings=require_face_phase_material_bindings, require_phase_bindings=require_face_phase_material_bindings)
    if not binding_validation.get("ok"):
        blockers.extend(str(x) for x in binding_validation.get("blockers", []))
    warnings.extend(str(x) for x in binding_validation.get("warnings", []))
    store = getattr(project, "cad_shape_store", None)
    imported_shapes = [] if store is None else [s for s in store.shapes.values() if s.backend == "step_ifc_import" or s.metadata.get("source_format") in {"step", "ifc"}]
    native_shapes = [s for s in imported_shapes if bool(s.metadata.get("native_brep_certified")) and bool(s.native_shape_available)]
    native_brep_certified = bool(native_shapes)
    if require_native_brep and not native_brep_certified:
        blockers.append("Native BRep-certified import acceptance requires at least one imported shape with native_brep_certified=true and native_shape_available=true.")
    elif not native_brep_certified:
        warnings.append("1.4.4 accepted imported topology/material/phase binding with native BRep certification false in this run.")
    cap = probe_native_brep_capability().to_dict()
    topology_binding_count = int(binding_validation.get("binding_count", 0))
    face_binding_count = int(binding_validation.get("face_binding_count", 0))
    edge_binding_count = int(binding_validation.get("edge_binding_count", 0))
    material_binding_count = int(binding_validation.get("material_binding_count", 0))
    phase_binding_count = int(binding_validation.get("phase_binding_count", 0))
    accepted = not blockers
    if accepted and native_brep_certified:
        status = "accepted_1_4_4_native_brep_topology_binding"
    elif accepted:
        status = "accepted_1_4_4_topology_binding"
    else:
        status = "rejected_1_4_4_topology_binding"
    return Release144AcceptanceReport(
        status=status,
        accepted=accepted,
        native_brep_certified=native_brep_certified,
        native_import_acceptance=bool(accepted and native_brep_certified),
        imported_shape_count=len(imported_shapes),
        topology_binding_count=topology_binding_count,
        face_binding_count=face_binding_count,
        edge_binding_count=edge_binding_count,
        material_binding_count=material_binding_count,
        phase_binding_count=phase_binding_count,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        blockers=blockers,
        warnings=warnings,
        metadata={
            "release": __version__,
            "require_native_brep": bool(require_native_brep),
            "native_brep_capability": cap,
            "step_ifc_validation": step_validation,
            "topology_binding_validation": binding_validation,
            "cad_shape_store_summary": {} if store is None else store.summary(),
        },
    )


__all__ = ["Release144AcceptanceReport", "audit_release_1_4_4"]
