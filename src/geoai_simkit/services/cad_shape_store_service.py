from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from geoai_simkit._version import __version__
from geoai_simkit.geoproject.cad_shape_store import CadShapeStore, CadShapeRecord, CadSerializedShapeReference, CadTopologyRecord, CadEntityBinding, CadOperationHistoryRecord, stable_ref_hash

@dataclass(slots=True)
class CadShapeStoreBuildReport:
    contract: str="geoai_simkit_cad_shape_store_build_v1"; ok: bool=False; status: str="not_run"; native_brep_available: bool=False; brep_serialization_mode: str="brep_json_surrogate"; shape_count:int=0; serialized_ref_count:int=0; topology_record_count:int=0; entity_binding_count:int=0; operation_count:int=0; exported_store_path:str=""; exported_reference_dir:str=""; warnings:list[str]=field(default_factory=list); metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return {"contract":self.contract,"ok":bool(self.ok),"status":self.status,"native_brep_available":bool(self.native_brep_available),"brep_serialization_mode":self.brep_serialization_mode,"shape_count":self.shape_count,"serialized_ref_count":self.serialized_ref_count,"topology_record_count":self.topology_record_count,"entity_binding_count":self.entity_binding_count,"operation_count":self.operation_count,"exported_store_path":self.exported_store_path,"exported_reference_dir":self.exported_reference_dir,"warnings":list(self.warnings),"metadata":dict(self.metadata)}

def _bounds(volume):
    b=getattr(volume,'bounds',None)
    if b is None or len(b)!=6: return None
    x0,x1,y0,y1,z0,z1=[float(v) for v in b]
    return (min(x0,x1),max(x0,x1),min(y0,y1),max(y0,y1),min(z0,z1),max(z0,z1))

def _topo(shape_id, entity_id, b):
    x0,x1,y0,y1,z0,z1=b; out=[CadTopologyRecord(f'{shape_id}:solid',shape_id,'solid',entity_id,persistent_name=f'{entity_id}/solid',bounds=b,metadata={'facade_topology':True})]
    for name,fb,n in [('xmin',(x0,x0,y0,y1,z0,z1),'-X'),('xmax',(x1,x1,y0,y1,z0,z1),'+X'),('ymin',(x0,x1,y0,y0,z0,z1),'-Y'),('ymax',(x0,x1,y1,y1,z0,z1),'+Y'),('zmin',(x0,x1,y0,y1,z0,z0),'-Z'),('zmax',(x0,x1,y0,y1,z1,z1),'+Z')]:
        out.append(CadTopologyRecord(f'{shape_id}:face:{name}',shape_id,'face',entity_id,parent_id=f'{shape_id}:solid',persistent_name=f'{entity_id}/face/{name}',bounds=fb,orientation=n,metadata={'facade_topology':True,'normal':n}))
    for i in range(12): out.append(CadTopologyRecord(f'{shape_id}:edge:{i:02d}',shape_id,'edge',entity_id,parent_id=f'{shape_id}:solid',persistent_name=f'{entity_id}/edge/{i:02d}',metadata={'facade_topology':True}))
    for i in range(8): out.append(CadTopologyRecord(f'{shape_id}:vertex:{i:02d}',shape_id,'vertex',entity_id,parent_id=f'{shape_id}:solid',persistent_name=f'{entity_id}/vertex/{i:02d}',metadata={'facade_topology':True}))
    return out

def _phase_ids(project, vid):
    pm=getattr(project,'phase_manager',None); out=[]
    if pm is None: return out
    for st in [getattr(pm,'initial_phase',None),*list(getattr(pm,'construction_phases',{}).values())]:
        if st is not None and vid in getattr(st,'active_blocks',set()): out.append(str(st.id))
    return out

def build_cad_shape_store(project:Any, *, output_dir:str|Path|None=None, attach:bool=True, include_roundtrip:bool=True, export_references:bool=False)->CadShapeStoreBuildReport:
    store=CadShapeStore(metadata={'release':__version__,'created_by':'build_cad_shape_store','native_brep_certified':False,'serialization_policy':'native BRep ref when present, brep_json surrogate otherwise'})
    warnings=[]; ref_dir=None
    if output_dir is not None:
        ref_dir=Path(output_dir)/'cad_shape_refs'
        if export_references: ref_dir.mkdir(parents=True,exist_ok=True)
    for vid,vol in dict(getattr(getattr(project,'geometry_model',None),'volumes',{})).items():
        b=_bounds(vol)
        if b is None: warnings.append(f'Volume {vid} has no valid bounds.'); continue
        sid=f'shape_{vid}'; rid=f'ref_{sid}'; payload={'contract':'geoai_simkit_brep_json_surrogate_v1','kind':'box_solid','source_entity_id':vid,'bounds':list(b),'role':str(getattr(vol,'role','unknown')),'material_id':str(getattr(vol,'material_id','') or ''),'native_brep_certified':False}; digest=stable_ref_hash(payload); path=''; storage='inline'
        if ref_dir is not None and export_references:
            po=ref_dir/f'{sid}.brep.json'; po.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); path=str(po); storage='external_file'
        store.serialized_refs[rid]=CadSerializedShapeReference(rid,'cad_facade','brep_json',storage,path,digest,payload if storage=='inline' else {'digest':digest,'source_entity_id':vid},{'native_brep_certified':False})
        topo=_topo(sid,vid,b)
        for r in topo: store.topology_records[r.id]=r
        ph=_phase_ids(project,vid); mat=str(getattr(vol,'material_id','') or '')
        store.shapes[sid]=CadShapeRecord(sid,str(getattr(vol,'name',vid)),'solid',[vid],rid,'cad_facade',False,True,[r.id for r in topo],mat,ph,{'bounds':list(b),'role':str(getattr(vol,'role','unknown')),'native_brep_certified':False})
        store.entity_bindings[f'binding_{vid}']=CadEntityBinding(f'binding_{vid}',vid,'volume',sid,[r.id for r in topo],'volume_owns_cad_shape',mat,ph,{'source':'build_cad_shape_store'})
    if include_roundtrip:
        rt=dict(getattr(getattr(project,'mesh_model',None),'metadata',{}).get('last_gmsh_occ_boolean_mesh_roundtrip',{}) or {})
        if rt:
            opid='operation_roundtrip_001'; store.operation_history[opid]=CadOperationHistoryRecord(opid,'gmsh_occ_boolean_mesh_roundtrip',[f'shape_{v}' for v in list(rt.get('consumed_volume_ids',[]) or []) if f'shape_{v}' in store.shapes],[f'shape_{v}' for v in list(rt.get('generated_volume_ids',[]) or []) if f'shape_{v}' in store.shapes],[str(v) for v in list(rt.get('consumed_volume_ids',[]) or [])],[str(v) for v in list(rt.get('generated_volume_ids',[]) or [])],str(rt.get('backend','unknown')),bool(rt.get('native_backend_used',False)),bool(rt.get('fallback_used',True)),str(rt.get('status','recorded')),{"roundtrip":rt})
        else: warnings.append('No 1.4.2c roundtrip report found; geometry-derived references only.')
    store.metadata['summary']=store.summary()
    if attach:
        project.cad_shape_store=store; project.metadata['release_1_4_2d_cad_shape_store']=store.summary()
        if hasattr(project,'mark_changed'): project.mark_changed(['geometry','topology','cad_shape_store'],action='build_cad_shape_store',affected_entities=list(store.shapes))
    store_path=''
    if output_dir is not None:
        root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); store_path=str(root/'cad_shape_store.json'); Path(store_path).write_text(json.dumps(store.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
    return CadShapeStoreBuildReport(
        ok=bool(store.shapes and store.serialized_refs and store.topology_records),
        status='cad_shape_store_ready' if store.shapes else 'cad_shape_store_incomplete',
        native_brep_available=False,
        brep_serialization_mode='brep_json_surrogate',
        shape_count=len(store.shapes),
        serialized_ref_count=len(store.serialized_refs),
        topology_record_count=len(store.topology_records),
        entity_binding_count=len(store.entity_bindings),
        operation_count=len(store.operation_history),
        exported_store_path=store_path,
        exported_reference_dir='' if ref_dir is None else str(ref_dir),
        warnings=warnings,
        metadata={'store_summary': store.summary(), 'release': __version__},
    )

def validate_cad_shape_store(project:Any)->dict[str,Any]:
    store=getattr(project,'cad_shape_store',None); blockers=[]; warnings=[]
    if store is None: return {'contract':'geoai_simkit_cad_shape_store_validation_v1','ok':False,'blockers':['GeoProjectDocument has no cad_shape_store attribute.'],'warnings':[]}
    if getattr(store,'contract','')!='geoproject_cad_shape_store_v1': blockers.append('Unexpected CadShapeStore contract.')
    if not store.shapes: blockers.append('CadShapeStore has no shape records.')
    if not store.serialized_refs: blockers.append('CadShapeStore has no serialized shape references.')
    if not store.topology_records: blockers.append('CadShapeStore has no topology records.')
    for sid,shape in store.shapes.items():
        if shape.serialized_ref_id not in store.serialized_refs: blockers.append(f'Shape {sid} missing serialized ref {shape.serialized_ref_id}.')
        missing=[tid for tid in shape.topology_ids if tid not in store.topology_records]
        if missing: blockers.append(f'Shape {sid} missing topology records: {missing[:3]}.')
    if not any(s.native_shape_available for s in store.shapes.values()): warnings.append('Serialized BRep surrogate references only; native BRep is not certified in this run.')
    return {'contract':'geoai_simkit_cad_shape_store_validation_v1','ok':not blockers,'blockers':blockers,'warnings':warnings,'summary':store.summary()}
