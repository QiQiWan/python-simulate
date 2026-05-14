from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from geoai_simkit._version import __version__
from geoai_simkit.commands.cad_kernel_commands import BuildCadShapeStoreCommand, ExecuteGmshOccBooleanMeshRoundtripCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.commands.interactive_geometry_commands import BooleanGeometryCommand
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.cad_shape_store_service import validate_cad_shape_store
from geoai_simkit.services.release_acceptance_142d import audit_release_1_4_2d

@dataclass(slots=True)
class Release142dArtifacts:
    project_path:str=''; shape_store_path:str=''; shape_store_build_path:str=''; shape_store_validation_path:str=''; acceptance_path:str=''; tutorial_path:str=''; reference_dir:str=''; metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return {'project_path':self.project_path,'shape_store_path':self.shape_store_path,'shape_store_build_path':self.shape_store_build_path,'shape_store_validation_path':self.shape_store_validation_path,'acceptance_path':self.acceptance_path,'tutorial_path':self.tutorial_path,'reference_dir':self.reference_dir,'metadata':dict(self.metadata)}

def _write_json(path:Path,payload:Any)->str:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); return str(path)

def _write_tutorial(path:Path, *, accepted:bool)->str:
    txt='\n'.join(['# GeoAI SimKit 1.4.2d CadShapeStore / BRep Serialized References','','This workflow builds a persistent CAD shape store after the 1.4.2c gmsh/OCC roundtrip.','It stores shape records, serialized BRep references, topology records, entity bindings and operation history.','Native BRep references are supported when present; deterministic `brep_json` references are marked as non-certified surrogates.','',f'Acceptance in this run: `{accepted}`'])
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(txt,encoding='utf-8'); return str(path)

def run_release_1_4_2d_workflow(output_dir:str|Path='docs/release/release_1_4_2d_cad_shape_store_review_bundle', *, require_native_brep:bool=False)->dict[str,Any]:
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); project=load_demo_project('foundation_pit_3d_beta'); project.metadata['release']=__version__; ids=list(project.geometry_model.volumes)[:2]
    if len(ids)<2: raise RuntimeError('1.4.2d workflow requires at least two demo volumes.')
    stack=CommandStack(); rr=stack.execute(BooleanGeometryCommand(operation='union',target_ids=tuple(ids)),project)
    if not rr.ok: raise RuntimeError(rr.message or 'Boolean feature record failed')
    rt=stack.execute(ExecuteGmshOccBooleanMeshRoundtripCommand(output_dir=str(root),stem='release_1_4_2d_gmsh_occ',require_native=False),project)
    if not rt.ok: raise RuntimeError(rt.message or 'Roundtrip failed')
    sr=stack.execute(BuildCadShapeStoreCommand(output_dir=str(root),include_roundtrip=True,export_references=True),project)
    if not sr.ok: raise RuntimeError(sr.message or 'CadShapeStore build failed')
    build=dict(sr.metadata or {}); validation=validate_cad_shape_store(project); acceptance=audit_release_1_4_2d(project,require_native_brep=require_native_brep)
    artifacts=Release142dArtifacts(project_path=str(project.save_json(root/'release_1_4_2d_project.geoproject.json')),shape_store_path=_write_json(root/'release_1_4_2d_cad_shape_store.json',project.cad_shape_store.to_dict()),shape_store_build_path=_write_json(root/'release_1_4_2d_cad_shape_store_build.json',build),shape_store_validation_path=_write_json(root/'release_1_4_2d_cad_shape_store_validation.json',validation),acceptance_path=_write_json(root/'release_1_4_2d_acceptance.json',acceptance.to_dict()),tutorial_path=_write_tutorial(root/'release_1_4_2d_tutorial.md',accepted=acceptance.accepted),reference_dir=str(root/'cad_shape_refs'),metadata={'release':__version__,'require_native_brep':bool(require_native_brep)})
    return {'contract':'geoai_simkit_release_1_4_2d_cad_shape_store_workflow_v1','ok':bool(acceptance.accepted),'project':project,'shape_store_build':build,'shape_store_validation':validation,'acceptance':acceptance.to_dict(),'artifacts':artifacts.to_dict()}
