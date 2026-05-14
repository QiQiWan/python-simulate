from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from geoai_simkit._version import __version__
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.step_ifc_shape_import import probe_step_ifc_import_capability, import_step_ifc_solid_topology, validate_step_ifc_shape_bindings
from geoai_simkit.services.release_acceptance_143 import audit_release_1_4_3

@dataclass(slots=True)
class Release143Artifacts:
    project_path: str = ''
    capability_path: str = ''
    import_path: str = ''
    validation_path: str = ''
    acceptance_path: str = ''
    tutorial_path: str = ''
    source_path: str = ''
    reference_dir: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return {'project_path':self.project_path,'capability_path':self.capability_path,'import_path':self.import_path,'validation_path':self.validation_path,'acceptance_path':self.acceptance_path,'tutorial_path':self.tutorial_path,'source_path':self.source_path,'reference_dir':self.reference_dir,'metadata':dict(self.metadata)}

def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'); return str(path)

def _write_sample_step(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'solids':[{'id':'step_demo_wall','name':'STEP Demo Retaining Wall','bounds':[-8.0,-7.2,-5.0,5.0,-8.0,0.0],'role':'imported_wall','material_id':'concrete'},{'id':'step_demo_slab','name':'STEP Demo Base Slab','bounds':[-8.0,8.0,-5.0,5.0,-8.4,-8.0],'role':'imported_slab','material_id':'concrete'}]}
    text = "ISO-10303-21;\nHEADER;FILE_DESCRIPTION(('GeoAI SimKit 1.4.3 sample'),'2;1');ENDSEC;\nDATA;\n#1=CARTESIAN_POINT('',(-8.0,-5.0,-8.4));\n#2=CARTESIAN_POINT('',(8.0,5.0,0.0));\n/* GEOAI_SIMKIT_SOLIDS: " + json.dumps(payload) + " */\nENDSEC;\nEND-ISO-10303-21;\n"
    path.write_text(text, encoding='utf-8'); return str(path)

def _write_tutorial(path: Path, *, accepted: bool, native: bool) -> str:
    text='\n'.join(['# GeoAI SimKit 1.4.3 STEP/IFC Solid Topology Import and Native Shape Binding','',f'Accepted: `{accepted}`',f'Native BRep certified in this run: `{native}`','', 'This release binds STEP/IFC solid references into CadShapeStore. If native runtimes are unavailable, imported solids are stored as explicit serialized topology references and are not reported as native BRep-certified.','', 'Recommended flow:', '1. Open the six-phase workbench.', '2. Import a STEP or IFC solid file.', '3. Inspect CadShapeStore imported shape references and topology records.', '4. Build mesh/physical groups after confirming material and phase bindings.'])
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8'); return str(path)

def run_release_1_4_3_workflow(output_dir: str|Path='docs/release/release_1_4_3_step_ifc_shape_binding_review_bundle', *, source_path: str|Path|None=None, require_native_brep: bool=False) -> dict[str, Any]:
    root=Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    project=load_demo_project('foundation_pit_3d_beta'); project.metadata['release']=__version__
    src=Path(source_path) if source_path is not None else root/'sample_step_import.step'
    if source_path is None: _write_sample_step(src)
    capability=probe_step_ifc_import_capability().to_dict()
    report=import_step_ifc_solid_topology(project, src, output_dir=root, attach=True, require_native=require_native_brep, export_references=True)
    if not report.ok: raise RuntimeError('STEP/IFC import failed: '+str(report.to_dict()))
    validation=validate_step_ifc_shape_bindings(project)
    acceptance=audit_release_1_4_3(project, require_native_brep=require_native_brep)
    artifacts=Release143Artifacts(project_path=str(project.save_json(root/'release_1_4_3_project.geoproject.json')),capability_path=_write_json(root/'release_1_4_3_step_ifc_capability.json',capability),import_path=_write_json(root/'release_1_4_3_step_ifc_import.json',report.to_dict()),validation_path=_write_json(root/'release_1_4_3_step_ifc_validation.json',validation),acceptance_path=_write_json(root/'release_1_4_3_acceptance.json',acceptance.to_dict()),tutorial_path=_write_tutorial(root/'release_1_4_3_tutorial.md',accepted=acceptance.accepted,native=acceptance.native_brep_certified),source_path=str(src),reference_dir=report.reference_dir,metadata={'release':__version__,'require_native_brep':bool(require_native_brep)})
    return {'contract':'geoai_simkit_release_1_4_3_step_ifc_shape_binding_workflow_v1','ok':bool(acceptance.accepted),'project':project,'capability':capability,'import_report':report.to_dict(),'validation':validation,'acceptance':acceptance.to_dict(),'artifacts':artifacts.to_dict()}
