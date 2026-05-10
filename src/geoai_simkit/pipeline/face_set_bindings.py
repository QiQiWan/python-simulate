from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, InterfaceDefinition, LoadDefinition, SimulationModel


def _as_int_tuple(values: Iterable[Any]) -> tuple[int, ...]:
    out: list[int] = []
    for value in list(values or []):
        try:
            out.append(int(value))
        except Exception:
            continue
    return tuple(dict.fromkeys(out))


def _face_set_lookup(model: SimulationModel) -> dict[str, dict[str, Any]]:
    meta = dict(model.metadata or {})
    payload = dict(meta.get('mesh.face_sets', {}) or {})
    rows = [dict(row) for row in list(payload.get('face_sets', []) or []) if isinstance(row, dict)]
    if not rows:
        rows = [dict(row) for row in list(meta.get('geometry.solver_face_set_rows', []) or []) if isinstance(row, dict)]
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get('name') or row.get('face_set_name') or '')
        entity_id = str(row.get('entity_id') or row.get('topology_entity_id') or dict(row.get('metadata', {}) or {}).get('topology_entity_id') or '')
        meta_row = dict(row.get('metadata', {}) or {})
        protected = str(meta_row.get('protected_surface') or row.get('protected_surface') or '')
        keys = [name, f'face_set:{name}' if name else '', entity_id, f'protected_surface:{protected}' if protected else '']
        if row.get('physical_id') is not None:
            keys.append(f'physical_surface:{int(row.get("physical_id"))}')
        if row.get('occ_surface_tag') is not None:
            keys.append(f'occ_surface:{int(row.get("occ_surface_tag"))}')
        for key in keys:
            if key:
                lookup[str(key)] = row
    return lookup


def _flat_node_ids(row: dict[str, Any]) -> tuple[int, ...]:
    raw = row.get('node_ids', []) or row.get('point_ids', []) or []
    flat: list[int] = []
    for item in list(raw or []):
        if isinstance(item, (list, tuple)):
            flat.extend(_as_int_tuple(item))
        else:
            try:
                flat.append(int(item))
            except Exception:
                pass
    return tuple(dict.fromkeys(flat))


def _tri_node_faces(row: dict[str, Any]) -> tuple[tuple[int, int, int], ...]:
    faces: list[tuple[int, int, int]] = []
    for item in list(row.get('node_ids', []) or []):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        try:
            faces.append((int(item[0]), int(item[1]), int(item[2])))
        except Exception:
            continue
    return tuple(faces)


def _stage_by_name(model: SimulationModel, stage_name: str) -> AnalysisStage | None:
    target = str(stage_name or '')
    for stage in model.stages:
        if str(stage.name) == target:
            return stage
    return None


def _make_bc(name: str, row: dict[str, Any], face_set: dict[str, Any], *, source_entity: str) -> BoundaryCondition:
    comps = tuple(int(v) for v in list(row.get('components', (0, 1, 2)) or (0, 1, 2)))
    vals = tuple(float(v) for v in list(row.get('values', (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)))
    metadata = dict(row.get('metadata', {}) or {})
    metadata.update({
        'point_ids': _flat_node_ids(face_set),
        'face_node_ids': [list(face) for face in _tri_node_faces(face_set)],
        'face_set_name': str(face_set.get('name') or ''),
        'face_set_physical_id': face_set.get('physical_id'),
        'source_entity': source_entity,
        'resolved_by': 'pipeline.face_set_bindings',
        'point_id_space': 'global',
    })
    return BoundaryCondition(name=name, kind=str(row.get('kind') or 'displacement'), target='point_ids', components=comps, values=vals, metadata=metadata)


def _values3(row: dict[str, Any], default: tuple[float, float, float]) -> np.ndarray:
    values = row.get('values', default)
    if isinstance(values, (int, float)):
        return np.asarray([0.0, 0.0, float(values)], dtype=float)
    arr = np.asarray(list(values or default), dtype=float).reshape(-1)
    out = np.zeros(3, dtype=float)
    out[: min(3, arr.size)] = arr[: min(3, arr.size)]
    return out


def _equivalent_nodal_forces(row: dict[str, Any], face_set: dict[str, Any]) -> tuple[list[dict[str, Any]], tuple[float, float, float]]:
    """Convert a FaceSet surface load into solver-ready nodal forces.

    The GUI still binds the load to an editable face/face-set. This helper only
    generates the derived nodal forces after remeshing.
    """
    faces = _tri_node_faces(face_set)
    areas = [float(v) for v in list(face_set.get('areas', []) or [])]
    normals = [list(n)[:3] for n in list(face_set.get('normals', []) or [])]
    kind = str(row.get('kind') or 'surface_traction').lower()
    nodal: dict[int, np.ndarray] = {}
    total = np.zeros(3, dtype=float)
    for idx, tri in enumerate(faces):
        area = float(areas[idx]) if idx < len(areas) else float(face_set.get('area', 0.0) or 0.0) / max(1, len(faces))
        if 'pressure' in kind:
            pressure = float(row.get('pressure', row.get('value', 0.0) if not row.get('values') else list(row.get('values') or [0.0])[0]) or 0.0)
            normal = np.asarray(normals[idx] if idx < len(normals) else face_set.get('owner_to_neighbor_normal', (0.0, 0.0, 1.0)), dtype=float)
            norm = float(np.linalg.norm(normal))
            if norm <= 1.0e-30:
                normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
            else:
                normal = normal / norm
            face_force = pressure * area * normal
        else:
            traction = _values3(row, (0.0, 0.0, -1.0))
            face_force = traction * area
        share = face_force / float(max(1, len(tri)))
        total += face_force
        for nid in tri:
            nodal.setdefault(int(nid), np.zeros(3, dtype=float))
            nodal[int(nid)] += share
    rows = [{'node_id': int(nid), 'force': [float(v) for v in vec.tolist()]} for nid, vec in sorted(nodal.items())]
    return rows, (float(total[0]), float(total[1]), float(total[2]))


def _make_load(name: str, row: dict[str, Any], face_set: dict[str, Any], *, source_entity: str) -> LoadDefinition:
    vals = tuple(float(v) for v in _values3(row, (0.0, 0.0, -1.0)).tolist())
    nodal_rows, total_force = _equivalent_nodal_forces(row, face_set)
    metadata = dict(row.get('metadata', {}) or {})
    metadata.update({
        'point_ids': _flat_node_ids(face_set),
        'face_node_ids': [list(face) for face in _tri_node_faces(face_set)],
        'face_set_name': str(face_set.get('name') or ''),
        'face_set_physical_id': face_set.get('physical_id'),
        'source_entity': source_entity,
        'resolved_by': 'pipeline.face_set_bindings',
        'surface_area': float(face_set.get('area', 0.0) or 0.0),
        'surface_normals': list(face_set.get('normals', []) or [])[:10],
        'point_id_space': 'global',
        'nodal_forces': nodal_rows,
        'equivalent_total_force': [float(v) for v in total_force],
        'load_distribution': 'face_area_equivalent_nodal_forces',
    })
    return LoadDefinition(name=name, kind=str(row.get('kind') or 'surface_traction'), target='equivalent_nodal_forces', values=total_force if nodal_rows else vals, metadata=metadata)


def _make_interface(name: str, row: dict[str, Any], face_set: dict[str, Any], *, source_entity: str) -> InterfaceDefinition | None:
    owner_region = str(face_set.get('owner_region') or face_set.get('adjacent_region') or '')
    neighbor_region = str(face_set.get('neighbor_region') or '')
    node_ids = _flat_node_ids(face_set)
    if not node_ids:
        return None
    params = dict(row.get('parameters', {}) or {})
    metadata = dict(row.get('metadata', {}) or {})
    metadata.update({
        'source_entity': source_entity,
        'face_set_name': str(face_set.get('name') or ''),
        'face_set_physical_id': face_set.get('physical_id'),
        'slave_region': str(row.get('slave_region') or owner_region),
        'master_region': str(row.get('master_region') or neighbor_region or owner_region),
        'resolved_by': 'pipeline.face_set_bindings',
        'uses_solver_face_set_v2': True,
        'surface_area': float(face_set.get('area', 0.0) or 0.0),
        'face_set_node_ids': [list(face) for face in _tri_node_faces(face_set)],
        'face_set_areas': [float(v) for v in list(face_set.get('areas', []) or [])],
        'face_set_normals': list(face_set.get('normals', []) or []),
        'face_set_side': str(face_set.get('side') or 'boundary'),
        'interface_ready_duplicate_side': str(row.get('duplicate_side') or 'slave'),
    })
    return InterfaceDefinition(
        name=name,
        kind=str(row.get('kind') or row.get('interface_kind') or 'face_set_contact'),
        slave_point_ids=node_ids,
        master_point_ids=node_ids if not row.get('master_point_ids') else _as_int_tuple(row.get('master_point_ids', [])),
        parameters=params,
        active_stages=tuple(str(v) for v in list(row.get('active_stages', []) or []) if str(v)),
        metadata=metadata,
    )


def apply_face_set_topology_bindings(model: SimulationModel, topology_bindings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Materialize FaceSet v2 bindings into BCs, equivalent loads and interfaces.

    Face sets are derived mesh artifacts, but their bindings are owned by the
    editable entity/named-selection layer. This function resolves the latest
    remeshed face set and creates solver-readable objects without exposing mesh
    cells as direct user-editable objects.
    """
    bindings = dict(topology_bindings or {})
    if not bindings:
        bindings = dict(dict(model.metadata.get('geometry.editable_payload', {}) or {}).get('topology_entity_bindings', {}) or {})
    lookup = _face_set_lookup(model)
    created_bcs: list[dict[str, Any]] = []
    created_loads: list[dict[str, Any]] = []
    created_interfaces: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for entity, payload in bindings.items():
        entity_id = str(entity or '')
        if not entity_id.startswith(('face_set:', 'protected_surface:', 'face:')):
            continue
        binding = dict(payload or {})
        face_set = lookup.get(entity_id)
        if face_set is None and entity_id.startswith('face_set:'):
            face_set = lookup.get(entity_id.split(':', 1)[1])
        if face_set is None:
            face_set = next((row for row in lookup.values() if str(dict(row.get('metadata', {}) or {}).get('topology_entity_id') or '') == entity_id), None)
        if face_set is None:
            unresolved.append({'entity_id': entity_id, 'reason': 'no matching solver FaceSet v2 row'})
            continue
        for idx, bc_row in enumerate(list(binding.get('boundary_conditions', []) or []), start=1):
            if not isinstance(bc_row, dict):
                continue
            bc = _make_bc(str(bc_row.get('name') or f'{entity_id}:bc:{idx}'), bc_row, face_set, source_entity=entity_id)
            model.add_boundary_condition(bc)
            created_bcs.append({'name': bc.name, 'entity_id': entity_id, 'point_count': len(tuple(bc.metadata.get('point_ids', ()) or ())), 'face_set_name': face_set.get('name')})
        for idx, load_row in enumerate(list(binding.get('stage_loads', []) or []), start=1):
            if not isinstance(load_row, dict):
                continue
            load = _make_load(str(load_row.get('name') or f'{entity_id}:load:{idx}'), load_row, face_set, source_entity=entity_id)
            stage_name = str(load_row.get('stage_name') or '')
            stage = _stage_by_name(model, stage_name)
            if stage is not None:
                stage.loads = tuple([*stage.loads, load])
                created_loads.append({
                    'name': load.name,
                    'stage_name': stage.name,
                    'entity_id': entity_id,
                    'point_count': len(tuple(load.metadata.get('point_ids', ()) or ())),
                    'nodal_force_count': len(list(load.metadata.get('nodal_forces', []) or [])),
                    'face_set_name': face_set.get('name'),
                    'target': load.target,
                })
            else:
                model.metadata.setdefault('pipeline.pending_face_set_stage_loads', []).append({'entity_id': entity_id, 'stage_name': stage_name, 'load': {'name': load.name, 'kind': load.kind, 'target': load.target, 'metadata': dict(load.metadata)}})
                unresolved.append({'entity_id': entity_id, 'reason': f'stage not found for face-set load: {stage_name}'})
        interface_rows: list[dict[str, Any]] = []
        for key in ('interfaces', 'contact_pairs', 'interface_elements'):
            interface_rows.extend([dict(row) for row in list(binding.get(key, []) or []) if isinstance(row, dict)])
        if binding.get('contact') or binding.get('interface'):
            row = dict(binding.get('contact') or binding.get('interface') or {})
            interface_rows.append(row)
        for idx, interface_row in enumerate(interface_rows, start=1):
            interface = _make_interface(str(interface_row.get('name') or f'{entity_id}:interface:{idx}'), interface_row, face_set, source_entity=entity_id)
            if interface is None:
                unresolved.append({'entity_id': entity_id, 'reason': 'face-set interface has no nodes'})
                continue
            model.add_interface(interface)
            created_interfaces.append({'name': interface.name, 'entity_id': entity_id, 'point_count': len(interface.slave_point_ids), 'face_count': len(interface.metadata.get('face_set_node_ids', []) or []), 'face_set_name': face_set.get('name')})
    report = {
        'contract': 'face_set_topology_binding_materialization_v2',
        'created_boundary_conditions': created_bcs,
        'created_stage_loads': created_loads,
        'created_interfaces': created_interfaces,
        'unresolved': unresolved,
        'summary': {
            'boundary_condition_count': len(created_bcs),
            'stage_load_count': len(created_loads),
            'interface_count': len(created_interfaces),
            'unresolved_count': len(unresolved),
            'equivalent_nodal_force_load_count': sum(1 for row in created_loads if row.get('target') == 'equivalent_nodal_forces'),
        },
    }
    model.metadata['pipeline.face_set_binding_materialization'] = report
    return report


__all__ = ['apply_face_set_topology_bindings']
