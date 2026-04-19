from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from geoai_simkit.core.model import BoundaryCondition, InterfaceDefinition, LoadDefinition, MaterialDefinition, StructuralElementDefinition
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, BoundaryConditionSpec, ContactPairSpec, ExcavationStepSpec, GeometrySource, InterfaceGeneratorSpec, LoadSpec, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, RegionSelectorSpec, StageSpec, StructureGeneratorSpec

CASE_FILE_KIND = 'geoai-simkit.analysis-case'
CASE_FORMAT_VERSION = 4
SUPPORTED_CASE_FORMAT_VERSIONS = {1, 2, 3, 4}


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


def _selector_from_dict(payload: dict[str, Any] | None) -> RegionSelectorSpec | None:
    if not payload:
        return None
    return RegionSelectorSpec(
        names=tuple(str(v) for v in payload.get('names', ())),
        patterns=tuple(str(v) for v in payload.get('patterns', ())),
        metadata=dict(payload.get('metadata') or {}),
        exclude_names=tuple(str(v) for v in payload.get('exclude_names', ())),
        exclude_patterns=tuple(str(v) for v in payload.get('exclude_patterns', ())),
    )


def _bc_spec_from_dict(payload: dict[str, Any]) -> BoundaryConditionSpec:
    return BoundaryConditionSpec(
        name=str(payload['name']),
        kind=str(payload['kind']),
        target=str(payload.get('target', 'all')),
        region_names=tuple(str(v) for v in payload.get('region_names', ())),
        selector=_selector_from_dict(payload.get('selector')),
        components=tuple(int(v) for v in payload.get('components', (0, 1, 2))),
        values=tuple(float(v) for v in payload.get('values', (0.0, 0.0, 0.0))),
        metadata=dict(payload.get('metadata') or {}),
    )


def _load_spec_from_dict(payload: dict[str, Any]) -> LoadSpec:
    return LoadSpec(
        name=str(payload['name']),
        kind=str(payload['kind']),
        target=str(payload.get('target', 'all')),
        region_names=tuple(str(v) for v in payload.get('region_names', ())),
        selector=_selector_from_dict(payload.get('selector')),
        values=tuple(float(v) for v in payload.get('values', ())),
        metadata=dict(payload.get('metadata') or {}),
    )


def _bc_or_spec_from_dict(payload: dict[str, Any]):
    if payload.get('selector') is not None or payload.get('region_names'):
        return _bc_spec_from_dict(payload)
    return _bc_from_dict(payload)


def _load_or_spec_from_dict(payload: dict[str, Any]):
    if payload.get('selector') is not None or payload.get('region_names'):
        return _load_spec_from_dict(payload)
    return _load_from_dict(payload)


def _bc_from_dict(payload: dict[str, Any]) -> BoundaryCondition:
    return BoundaryCondition(
        name=str(payload['name']),
        kind=str(payload['kind']),
        target=str(payload['target']),
        components=tuple(int(v) for v in payload.get('components', (0, 1, 2))),
        values=tuple(float(v) for v in payload.get('values', (0.0, 0.0, 0.0))),
        metadata=dict(payload.get('metadata') or {}),
    )


def _load_from_dict(payload: dict[str, Any]) -> LoadDefinition:
    return LoadDefinition(
        name=str(payload['name']),
        kind=str(payload['kind']),
        target=str(payload['target']),
        values=tuple(float(v) for v in payload.get('values', ())),
        metadata=dict(payload.get('metadata') or {}),
    )


def _stage_from_dict(payload: dict[str, Any]) -> StageSpec:
    return StageSpec(
        name=str(payload['name']),
        predecessor=None if payload.get('predecessor') in {None, ''} else str(payload.get('predecessor')),
        activation_map={str(k): bool(v) for k, v in dict(payload.get('activation_map') or {}).items()} if payload.get('activation_map') is not None else None,
        activate_regions=tuple(str(v) for v in payload.get('activate_regions', ())),
        deactivate_regions=tuple(str(v) for v in payload.get('deactivate_regions', ())),
        activate_selector=_selector_from_dict(payload.get('activate_selector')),
        deactivate_selector=_selector_from_dict(payload.get('deactivate_selector')),
        boundary_conditions=tuple(_bc_or_spec_from_dict(item) for item in payload.get('boundary_conditions', ())),
        loads=tuple(_load_or_spec_from_dict(item) for item in payload.get('loads', ())),
        steps=payload.get('steps'),
        metadata=dict(payload.get('metadata') or {}),
    )


def _material_library_from_dict(payload: dict[str, Any]) -> MaterialDefinition:
    return MaterialDefinition(name=str(payload['name']), model_type=str(payload['model_type']), parameters=dict(payload.get('parameters') or {}), metadata=dict(payload.get('metadata') or {}))


def _structure_from_dict(payload: dict[str, Any]) -> StructuralElementDefinition:
    return StructuralElementDefinition(
        name=str(payload['name']),
        kind=str(payload['kind']),
        point_ids=tuple(int(v) for v in payload.get('point_ids', ())),
        parameters=dict(payload.get('parameters') or {}),
        active_stages=tuple(str(v) for v in payload.get('active_stages', ())),
        metadata=dict(payload.get('metadata') or {}),
    )


def _structure_generator_from_dict(payload: dict[str, Any]) -> StructureGeneratorSpec:
    return StructureGeneratorSpec(kind=str(payload['kind']), parameters=dict(payload.get('parameters') or {}), metadata=dict(payload.get('metadata') or {}))


def _structure_entry_from_dict(payload: dict[str, Any]) -> StructuralElementDefinition | StructureGeneratorSpec:
    if str(payload.get('entry_type') or '').strip().lower() == 'generator':
        return _structure_generator_from_dict(payload)
    return _structure_from_dict(payload)


def _structure_entry_to_dict(payload: StructuralElementDefinition | StructureGeneratorSpec) -> dict[str, Any]:
    if isinstance(payload, StructureGeneratorSpec):
        return {'entry_type': 'generator', 'kind': payload.kind, 'parameters': _to_plain(dict(payload.parameters or {})), 'metadata': _to_plain(dict(payload.metadata or {}))}
    out = _to_plain(payload)
    if isinstance(out, dict):
        out.setdefault('entry_type', 'explicit')
    return out


def _interface_from_dict(payload: dict[str, Any]) -> InterfaceDefinition:
    return InterfaceDefinition(
        name=str(payload['name']),
        kind=str(payload['kind']),
        slave_point_ids=tuple(int(v) for v in payload.get('slave_point_ids', ())),
        master_point_ids=tuple(int(v) for v in payload.get('master_point_ids', ())),
        parameters=dict(payload.get('parameters') or {}),
        active_stages=tuple(str(v) for v in payload.get('active_stages', ())),
        metadata=dict(payload.get('metadata') or {}),
    )


def _interface_generator_from_dict(payload: dict[str, Any]) -> InterfaceGeneratorSpec:
    return InterfaceGeneratorSpec(kind=str(payload['kind']), parameters=dict(payload.get('parameters') or {}), metadata=dict(payload.get('metadata') or {}))


def _interface_entry_from_dict(payload: dict[str, Any]) -> InterfaceDefinition | InterfaceGeneratorSpec:
    if str(payload.get('entry_type') or '').strip().lower() == 'generator':
        return _interface_generator_from_dict(payload)
    return _interface_from_dict(payload)


def _interface_entry_to_dict(payload: InterfaceDefinition | InterfaceGeneratorSpec) -> dict[str, Any]:
    if isinstance(payload, InterfaceGeneratorSpec):
        return {'entry_type': 'generator', 'kind': payload.kind, 'parameters': _to_plain(dict(payload.parameters or {})), 'metadata': _to_plain(dict(payload.metadata or {}))}
    out = _to_plain(payload)
    if isinstance(out, dict):
        out.setdefault('entry_type', 'explicit')
    return out


def _geometry_to_dict(geometry: GeometrySource) -> dict[str, Any]:
    if geometry.data is not None:
        raise ValueError('GeometrySource with in-memory mesh data cannot be serialized as a portable case file. Use kind/parameters or builder-backed sources instead.')
    if geometry.builder is not None and not geometry.kind:
        raise ValueError('GeometrySource with a custom builder requires a registered kind to be serialized.')
    return {'kind': geometry.kind, 'parameters': _to_plain(dict(geometry.parameters or {})), 'metadata': _to_plain(dict(geometry.metadata or {}))}


def case_spec_to_dict(spec: AnalysisCaseSpec) -> dict[str, Any]:
    return {
        'case_file_kind': CASE_FILE_KIND,
        'case_format_version': CASE_FORMAT_VERSION,
        'name': spec.name,
        'geometry': _geometry_to_dict(spec.geometry),
        'mesh': _to_plain(spec.mesh),
        'materials': _to_plain(spec.materials),
        'stages': _to_plain(spec.stages),
        'mesh_preparation': _to_plain(spec.mesh_preparation),
        'material_library': _to_plain(spec.material_library),
        'boundary_conditions': _to_plain(spec.boundary_conditions),
        'structures': [_structure_entry_to_dict(item) for item in spec.structures],
        'interfaces': [_interface_entry_to_dict(item) for item in spec.interfaces],
        'metadata': _to_plain(spec.metadata),
    }


def case_spec_from_dict(payload: dict[str, Any]) -> AnalysisCaseSpec:
    version = int(payload.get('case_format_version', 1) or 1)
    if version not in SUPPORTED_CASE_FORMAT_VERSIONS:
        raise ValueError(f'Unsupported case_format_version: {version}. Supported versions: {sorted(SUPPORTED_CASE_FORMAT_VERSIONS)}')
    case_kind = str(payload.get('case_file_kind') or CASE_FILE_KIND)
    if case_kind != CASE_FILE_KIND:
        raise ValueError(f'Unsupported case_file_kind: {case_kind!r}. Expected {CASE_FILE_KIND!r}.')
    geometry_payload = dict(payload.get('geometry') or {})
    geometry = GeometrySource(kind=geometry_payload.get('kind'), parameters=dict(geometry_payload.get('parameters') or {}), metadata=dict(geometry_payload.get('metadata') or {}))
    mesh_payload = dict(payload.get('mesh') or {})
    prep_payload = dict(payload.get('mesh_preparation') or {})
    return AnalysisCaseSpec(
        name=str(payload['name']),
        geometry=geometry,
        mesh=MeshAssemblySpec(**mesh_payload),
        materials=tuple(
            MaterialAssignmentSpec(
                region_names=tuple(str(v) for v in item.get('region_names', ())),
                selector=_selector_from_dict(item.get('selector')),
                material_name=str(item['material_name']),
                parameters=dict(item.get('parameters') or {}),
                metadata=dict(item.get('metadata') or {}),
            )
            for item in payload.get('materials', ())
        ),
        stages=tuple(_stage_from_dict(item) for item in payload.get('stages', ())),
        mesh_preparation=MeshPreparationSpec(
            excavation_steps=tuple(
                ExcavationStepSpec(
                    name=str(item['name']),
                    deactivate_regions=tuple(str(v) for v in item.get('deactivate_regions', ())),
                    activate_regions=tuple(str(v) for v in item.get('activate_regions', ())),
                    deactivate_selector=_selector_from_dict(item.get('deactivate_selector')),
                    activate_selector=_selector_from_dict(item.get('activate_selector')),
                    steps=item.get('steps'),
                    metadata=dict(item.get('metadata') or {}),
                )
                for item in prep_payload.get('excavation_steps', ())
            ),
            contact_pairs=tuple(
                ContactPairSpec(
                    name=str(item['name']),
                    slave_region=str(item.get('slave_region') or ''),
                    master_region=str(item.get('master_region') or ''),
                    slave_selector=_selector_from_dict(item.get('slave_selector')),
                    master_selector=_selector_from_dict(item.get('master_selector')),
                    active_stages=tuple(str(v) for v in item.get('active_stages', ())),
                    parameters=dict(item.get('parameters') or {}),
                    metadata=dict(item.get('metadata') or {}),
                    search_radius_factor=float(item.get('search_radius_factor', 1.75)),
                    exact_only=bool(item.get('exact_only', False)),
                )
                for item in prep_payload.get('contact_pairs', ())
            ),
            auto_interface_detection=bool(prep_payload.get('auto_interface_detection', True)),
            merge_coincident_points=bool(prep_payload.get('merge_coincident_points', True)),
            interface_node_split_mode=str(prep_payload.get('interface_node_split_mode', 'plan') or 'plan'),
            interface_duplicate_side=str(prep_payload.get('interface_duplicate_side', 'slave') or 'slave'),
            metadata=dict(prep_payload.get('metadata') or {}),
        ),
        material_library=tuple(_material_library_from_dict(item) for item in payload.get('material_library', ())),
        boundary_conditions=tuple(_bc_or_spec_from_dict(item) for item in payload.get('boundary_conditions', ())),
        structures=tuple(_structure_entry_from_dict(item) for item in payload.get('structures', ())),
        interfaces=tuple(_interface_entry_from_dict(item) for item in payload.get('interfaces', ())),
        metadata=dict(payload.get('metadata') or {}),
    )


def save_case_spec(spec: AnalysisCaseSpec, path: str | Path) -> Path:
    path = Path(path)
    suffix = path.suffix.lower()
    payload = case_spec_to_dict(spec)
    if suffix in {'.yaml', '.yml'}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError('YAML export requires PyYAML. Install it first, or use a .json path.') from exc
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding='utf-8')
        return path
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def load_case_spec(path: str | Path) -> AnalysisCaseSpec:
    path = Path(path)
    suffix = path.suffix.lower()
    text = path.read_text(encoding='utf-8')
    if suffix in {'.yaml', '.yml'}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError('YAML import requires PyYAML. Install it first, or use JSON case files.') from exc
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError('Case file must contain a mapping/object at the top level.')
    return case_spec_from_dict(payload)
