from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from geoai_simkit._version import __version__
from geoai_simkit.services.cad_shape_store_service import validate_cad_shape_store

@dataclass(slots=True)
class Release142dAcceptanceReport:
    contract: str='geoai_simkit_release_1_4_2d_cad_shape_store_acceptance_v1'; status:str='rejected_1_4_2d_cad_shape_store'; accepted:bool=False; native_brep_certified:bool=False; blocker_count:int=0; warning_count:int=0; blockers:list[str]=field(default_factory=list); warnings:list[str]=field(default_factory=list); metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return {'contract':self.contract,'status':self.status,'accepted':bool(self.accepted),'native_brep_certified':bool(self.native_brep_certified),'blocker_count':self.blocker_count,'warning_count':self.warning_count,'blockers':list(self.blockers),'warnings':list(self.warnings),'metadata':dict(self.metadata)}

def audit_release_1_4_2d(project:Any, *, require_native_brep:bool=False)->Release142dAcceptanceReport:
    blockers=[]; warnings=[]
    if __version__ not in {'1.4.2d-cad-shape-store', '1.4.3-step-ifc-shape-binding', '1.4.8-cad-fem-preprocessor', '1.4.9-p85-step-ifc-native-benchmark'}: blockers.append(f'Unexpected version: {__version__}')
    validation=validate_cad_shape_store(project)
    if not validation.get('ok'): blockers.extend(str(x) for x in validation.get('blockers',[]))
    warnings.extend(str(x) for x in validation.get('warnings',[]))
    store=getattr(project,'cad_shape_store',None); summary={} if store is None else store.summary()
    native=int(summary.get('native_shape_count',0) or 0); refs=int(summary.get('serialized_ref_count',0) or 0); topo=int(summary.get('topology_record_count',0) or 0); binds=int(summary.get('entity_binding_count',0) or 0)
    if refs<=0: blockers.append('CadShapeStore must contain serialized BRep/native-shape references.')
    if topo<=0: blockers.append('CadShapeStore must contain topology records for persistent naming.')
    if binds<=0: blockers.append('CadShapeStore must contain entity bindings back to GeoProject entities.')
    if require_native_brep and native<=0: blockers.append('Native BRep-certified acceptance requires at least one native shape reference.')
    if native<=0: warnings.append('1.4.2d accepted serialized BRep surrogate references; native BRep certification remains false in this run.')
    rt=dict(getattr(getattr(project,'mesh_model',None),'metadata',{}).get('last_gmsh_occ_boolean_mesh_roundtrip',{}) or {})
    if not rt: warnings.append('No 1.4.2c mesh roundtrip report was found before CadShapeStore build.')
    br=dict(getattr(project,'metadata',{}).get('release_1_4_2d_cad_shape_store_build',{}) or {})
    if br and not br.get('ok'): blockers.append('CadShapeStore build report is present but not ok.')
    accepted=not blockers
    status='accepted_1_4_2d_native_brep_store' if accepted and native>0 else ('accepted_1_4_2d_cad_shape_store' if accepted else 'rejected_1_4_2d_cad_shape_store')
    return Release142dAcceptanceReport(status=status,accepted=accepted,native_brep_certified=bool(native>0),blocker_count=len(blockers),warning_count=len(warnings),blockers=blockers,warnings=warnings,metadata={'release':__version__,'require_native_brep':bool(require_native_brep),'validation':validation,'cad_shape_store_summary':summary,'roundtrip':rt,'build_report':br})
