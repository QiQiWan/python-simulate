from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable

_GEOMETRY_KEYS = {
    'blocks', 'editable_blocks', 'block_splits', 'wall_alignments', 'slope_surfaces',
    'terrain_surfaces', 'stratigraphy', 'pit_modeling', 'sketch_features',
}
_MESH_CONTROL_KEYS = {'mesh_size_controls'}
_DERIVED_KEYS = {
    'brep_document', 'solver_face_set_rows', 'mesh_quality_report',
    'selected_topology_entity', 'selected_block_name', 'selected_face_name',
}


def _stable_json(value: Any) -> str:
    def normalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {str(k): normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, (list, tuple, set)):
            return [normalize(v) for v in obj]
        if isinstance(obj, float):
            return round(float(obj), 12)
        if isinstance(obj, (str, int, bool)) or obj is None:
            return obj
        return str(obj)
    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def stable_hash(value: Any) -> str:
    return sha256(_stable_json(value).encode('utf-8')).hexdigest()[:16]


def geometry_signature(parameters: dict[str, Any] | None) -> str:
    params = dict(parameters or {})
    payload = {key: params.get(key) for key in sorted(_GEOMETRY_KEYS) if key in params}
    return stable_hash(payload)


def mesh_signature(parameters: dict[str, Any] | None, *, mesh_options: dict[str, Any] | None = None) -> str:
    params = dict(parameters or {})
    payload = {
        'geometry': {key: params.get(key) for key in sorted(_GEOMETRY_KEYS) if key in params},
        'mesh_controls': {key: params.get(key) for key in sorted(_MESH_CONTROL_KEYS) if key in params},
        'mesh_options': dict(mesh_options or {}),
    }
    return stable_hash(payload)


def clear_derived_geometry_cache(parameters: dict[str, Any], *, keep_selection: bool = True) -> dict[str, Any]:
    out = dict(parameters or {})
    for key in _DERIVED_KEYS:
        if keep_selection and key in {'selected_topology_entity', 'selected_block_name', 'selected_face_name'}:
            continue
        out.pop(key, None)
    return out


@dataclass(slots=True)
class GeometryDirtyState:
    geometry_signature: str
    mesh_signature: str
    mesh_status: str = 'stale'
    result_status: str = 'stale'
    solver_status: str = 'stale'
    reason: str = 'geometry_changed'
    invalidated: tuple[str, ...] = ('mesh', 'results', 'solver_package')
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'geometry_dirty_state_v1',
            'geometry_signature': self.geometry_signature,
            'mesh_signature': self.mesh_signature,
            'mesh_status': self.mesh_status,
            'result_status': self.result_status,
            'solver_status': self.solver_status,
            'reason': self.reason,
            'invalidated': list(self.invalidated),
            'requires_remesh': self.mesh_status != 'current',
            'requires_resolve': self.result_status != 'current' or self.solver_status != 'current',
            'metadata': dict(self.metadata),
        }


class GeometryDirtyStateManager:
    """Track that users edit entities while meshes/results are generated artifacts."""

    def mark_geometry_changed(self, parameters: dict[str, Any], *, reason: str = 'geometry_changed', keep_selection: bool = True) -> dict[str, Any]:
        params = clear_derived_geometry_cache(dict(parameters or {}), keep_selection=keep_selection)
        state = GeometryDirtyState(
            geometry_signature=geometry_signature(params),
            mesh_signature=mesh_signature(params),
            reason=str(reason or 'geometry_changed'),
            invalidated=('mesh', 'face_sets', 'results', 'solver_package'),
        ).to_dict()
        params['geometry_dirty_state'] = state
        return params

    def mark_mesh_controls_changed(self, parameters: dict[str, Any], *, reason: str = 'mesh_control_changed') -> dict[str, Any]:
        params = dict(parameters or {})
        state = GeometryDirtyState(
            geometry_signature=geometry_signature(params),
            mesh_signature=mesh_signature(params),
            reason=str(reason or 'mesh_control_changed'),
            invalidated=('mesh', 'face_sets', 'results', 'solver_package'),
        ).to_dict()
        params['geometry_dirty_state'] = state
        return params

    def mark_bindings_changed(self, parameters: dict[str, Any], *, reason: str = 'entity_binding_changed') -> dict[str, Any]:
        params = dict(parameters or {})
        prior = dict(params.get('geometry_dirty_state') or {})
        prior.update({
            'contract': 'geometry_dirty_state_v1',
            'geometry_signature': geometry_signature(params),
            'mesh_signature': mesh_signature(params),
            'result_status': 'stale',
            'solver_status': 'stale',
            'reason': str(reason or 'entity_binding_changed'),
            'invalidated': list(dict.fromkeys(list(prior.get('invalidated', []) or []) + ['results', 'solver_package'])),
            'requires_resolve': True,
        })
        params['geometry_dirty_state'] = prior
        return params

    def mark_mesh_current(self, parameters: dict[str, Any], *, mesh_options: dict[str, Any] | None = None, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(parameters or {})
        state = {
            'contract': 'geometry_dirty_state_v1',
            'geometry_signature': geometry_signature(params),
            'mesh_signature': mesh_signature(params),
            'mesh_status': 'current',
            'result_status': 'stale',
            'solver_status': 'stale',
            'reason': 'mesh_regenerated_from_current_entities',
            'invalidated': ['results', 'solver_package'],
            'requires_remesh': False,
            'requires_resolve': True,
            'metadata': {'mesh_summary': dict(summary or {})},
        }
        params['geometry_dirty_state'] = state
        return params


def summarize_dirty_state(parameters: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(parameters or {})
    state = dict(params.get('geometry_dirty_state') or {})
    current_geometry = geometry_signature(params)
    current_mesh = mesh_signature(params)
    if not state:
        state = GeometryDirtyState(current_geometry, current_mesh, reason='not_tracked').to_dict()
    state['current_geometry_signature'] = current_geometry
    state['current_mesh_signature'] = current_mesh
    state['geometry_signature_match'] = str(state.get('geometry_signature') or '') == current_geometry
    state['mesh_signature_match'] = str(state.get('mesh_signature') or '') == current_mesh
    if not state['geometry_signature_match'] or not state['mesh_signature_match']:
        state['requires_remesh'] = True
        state['mesh_status'] = 'stale'
    return state


__all__ = [
    'GeometryDirtyState', 'GeometryDirtyStateManager', 'clear_derived_geometry_cache',
    'geometry_signature', 'mesh_signature', 'stable_hash', 'summarize_dirty_state',
]
