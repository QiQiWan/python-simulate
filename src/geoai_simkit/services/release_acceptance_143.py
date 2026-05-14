from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from geoai_simkit._version import __version__
from geoai_simkit.services.step_ifc_shape_import import validate_step_ifc_shape_bindings

@dataclass(slots=True)
class Release143AcceptanceReport:
    contract: str = 'geoai_simkit_release_1_4_3_step_ifc_shape_binding_acceptance_v1'
    status: str = 'rejected_1_4_3_step_ifc_shape_binding'
    accepted: bool = False
    native_brep_certified: bool = False
    imported_shape_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {'contract':self.contract,'status':self.status,'accepted':bool(self.accepted),'native_brep_certified':bool(self.native_brep_certified),'imported_shape_count':int(self.imported_shape_count),'blocker_count':self.blocker_count,'warning_count':self.warning_count,'blockers':list(self.blockers),'warnings':list(self.warnings),'metadata':dict(self.metadata)}

def audit_release_1_4_3(project: Any, *, require_native_brep: bool=False) -> Release143AcceptanceReport:
    blockers: list[str] = []
    warnings: list[str] = []
    if __version__ not in {'1.4.3-step-ifc-shape-binding', '1.4.8-cad-fem-preprocessor', '1.4.9-p85-step-ifc-native-benchmark'}:
        blockers.append(f'Unexpected version: {__version__}')
    validation = validate_step_ifc_shape_bindings(project)
    if not validation.get('ok'):
        blockers.extend(str(x) for x in validation.get('blockers', []))
    warnings.extend(str(x) for x in validation.get('warnings', []))
    store = getattr(project, 'cad_shape_store', None)
    imported_shapes = [] if store is None else [s for s in store.shapes.values() if s.backend == 'step_ifc_import' or s.metadata.get('source_format') in {'step','ifc'}]
    native_count = sum(1 for s in imported_shapes if s.native_shape_available)
    if require_native_brep and native_count <= 0:
        blockers.append('Native BRep-certified STEP/IFC acceptance requires at least one native imported shape.')
    if native_count <= 0:
        warnings.append('1.4.3 accepted STEP/IFC serialized topology binding; native BRep certification remains false in this run.')
    last_import = dict(getattr(project, 'metadata', {}).get('release_1_4_3_step_ifc_import', {}) or {})
    if not last_import:
        blockers.append('No release_1_4_3_step_ifc_import metadata was found.')
    accepted = not blockers
    status = 'accepted_1_4_3_native_step_ifc_brep_binding' if accepted and native_count > 0 else ('accepted_1_4_3_step_ifc_shape_binding' if accepted else 'rejected_1_4_3_step_ifc_shape_binding')
    return Release143AcceptanceReport(status=status,accepted=accepted,native_brep_certified=bool(native_count>0),imported_shape_count=len(imported_shapes),blocker_count=len(blockers),warning_count=len(warnings),blockers=blockers,warnings=warnings,metadata={'release':__version__,'require_native_brep':bool(require_native_brep),'validation':validation,'last_import':last_import,'cad_shape_store_summary':{} if store is None else store.summary()})
