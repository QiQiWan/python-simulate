from __future__ import annotations
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from geoai_simkit.pipeline.specs import *
from geoai_simkit.core.model import MaterialDefinition

CASE_FILE_KIND = 'geoai_simkit.analysis_case'
CASE_FORMAT_VERSION = '0.8.36'
SUPPORTED_CASE_FORMAT_VERSIONS = ('0.8.36','0.8.35')

def _plain(obj: Any) -> Any:
    if is_dataclass(obj): return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, tuple): return [_plain(v) for v in obj]
    if isinstance(obj, list): return [_plain(v) for v in obj]
    if isinstance(obj, dict): return {str(k): _plain(v) for k, v in obj.items()}
    return obj

def case_spec_to_dict(case: AnalysisCaseSpec) -> dict[str, Any]:
    return {'kind': CASE_FILE_KIND, 'version': CASE_FORMAT_VERSION, 'case': _plain(case)}

def _tuple_dataclass(cls, rows):
    return tuple(cls(**dict(x)) if isinstance(x, dict) else x for x in list(rows or []))

def case_spec_from_dict(payload: dict[str, Any]) -> AnalysisCaseSpec:
    data = dict(payload.get('case', payload) or {})
    geometry = GeometrySource(**dict(data.get('geometry') or {}))
    mesh = MeshAssemblySpec(**dict(data.get('mesh') or {}))
    mp = MeshPreparationSpec(**{**dict(data.get('mesh_preparation') or {}), 'excavation_steps': _tuple_dataclass(ExcavationStepSpec, dict(data.get('mesh_preparation') or {}).get('excavation_steps', ())), 'contact_pairs': _tuple_dataclass(ContactPairSpec, dict(data.get('mesh_preparation') or {}).get('contact_pairs', ()))})
    mats = _tuple_dataclass(MaterialAssignmentSpec, data.get('materials', ()))
    bcs = _tuple_dataclass(BoundaryConditionSpec, data.get('boundary_conditions', ()))
    loads = _tuple_dataclass(LoadSpec, data.get('loads', ()))
    stages = _tuple_dataclass(StageSpec, data.get('stages', ()))
    structures = _tuple_dataclass(StructureGeneratorSpec, data.get('structures', ()))
    interfaces = _tuple_dataclass(InterfaceGeneratorSpec, data.get('interfaces', ()))
    lib = tuple(MaterialDefinition(**x) if isinstance(x, dict) and {'name','model_type'} <= set(x) else x for x in list(data.get('material_library', ()) or ()))
    return AnalysisCaseSpec(str(data.get('name','case')), geometry=geometry, mesh=mesh, material_library=lib, materials=mats, boundary_conditions=bcs, loads=loads, stages=stages, structures=structures, interfaces=interfaces, mesh_preparation=mp, metadata=dict(data.get('metadata') or {}))

def save_case_spec(case: AnalysisCaseSpec, path: str | Path) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(case_spec_to_dict(case), indent=2, ensure_ascii=False, default=str), encoding='utf-8'); return p

def load_case_spec(path: str | Path) -> AnalysisCaseSpec:
    return case_spec_from_dict(json.loads(Path(path).read_text(encoding='utf-8')))
