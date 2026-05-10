from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

TET_FACES: tuple[tuple[int, int, int], ...] = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))


def _tri_area_normal(points: np.ndarray, tri: Sequence[int]) -> tuple[float, tuple[float, float, float]]:
    p0, p1, p2 = (points[int(i)] for i in tri[:3])
    n = np.cross(p1 - p0, p2 - p0)
    area = 0.5 * float(np.linalg.norm(n))
    if area <= 1.0e-30:
        return 0.0, (0.0, 0.0, 0.0)
    n = n / (2.0 * area)
    return area, (float(n[0]), float(n[1]), float(n[2]))


def _physical_maps(mesh: Any) -> tuple[dict[int, str], dict[int, str]]:
    volume: dict[int, str] = {}
    surface: dict[int, str] = {}
    for name, raw in (getattr(mesh, 'field_data', {}) or {}).items():
        try:
            arr = np.asarray(raw).ravel()
            pid = int(arr[0])
            dim = int(arr[1]) if arr.size > 1 else -1
        except Exception:
            continue
        if dim == 3:
            volume[pid] = str(name)
        elif dim == 2:
            surface[pid] = str(name)
    return volume, surface


def _cell_data_array(mesh: Any, key: str, block_index: int, cell_type: str, n: int, default: int = 0) -> np.ndarray:
    cell_data = getattr(mesh, 'cell_data', {}) or {}
    if isinstance(cell_data, dict) and key in cell_data:
        try:
            return np.asarray(cell_data[key][block_index], dtype=np.int64)
        except Exception:
            pass
    cdict = getattr(mesh, 'cell_data_dict', {}) or {}
    if isinstance(cdict, dict):
        try:
            return np.asarray(cdict.get(key, {}).get(cell_type, np.full(n, default)), dtype=np.int64)
        except Exception:
            pass
    return np.full(n, default, dtype=np.int64)


def _normal_dot(a: Sequence[float], b: Sequence[float]) -> float:
    aa = np.asarray(list(a)[:3], dtype=float)
    bb = np.asarray(list(b)[:3], dtype=float)
    na = float(np.linalg.norm(aa))
    nb = float(np.linalg.norm(bb))
    if na <= 1.0e-30 or nb <= 1.0e-30:
        return 0.0
    return float(np.dot(aa / na, bb / nb))


@dataclass(frozen=True, slots=True)
class FaceSet:
    name: str
    physical_id: int
    physical_name: str = ''
    surface_role: str = 'boundary_surface'
    occ_surface_tag: int = 0
    adjacent_region: str = ''
    owner_region: str = ''
    neighbor_region: str = ''
    side: str = 'boundary'
    owner_cell_ids: tuple[int, ...] = ()
    owner_local_face_ids: tuple[int, ...] = ()
    neighbor_cell_ids: tuple[int, ...] = ()
    neighbor_local_face_ids: tuple[int, ...] = ()
    node_ids: tuple[tuple[int, int, int], ...] = ()
    normals: tuple[tuple[float, float, float], ...] = ()
    owner_to_neighbor_normal: tuple[float, float, float] = (0.0, 0.0, 0.0)
    areas: tuple[float, ...] = ()
    unmatched_node_faces: tuple[tuple[int, int, int], ...] = ()
    normal_consistency_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_area = float(sum(self.areas))
        return {
            'name': self.name,
            'physical_id': int(self.physical_id),
            'physical_name': self.physical_name,
            'surface_role': self.surface_role,
            'occ_surface_tag': int(self.occ_surface_tag),
            'adjacent_region': self.adjacent_region or self.owner_region,
            'owner_region': self.owner_region or self.adjacent_region,
            'neighbor_region': self.neighbor_region,
            'side': self.side,
            'boundary_cell_ids': [int(v) for v in self.owner_cell_ids],
            'local_face_ids': [int(v) for v in self.owner_local_face_ids],
            'owner_cell_ids': [int(v) for v in self.owner_cell_ids],
            'owner_local_face_ids': [int(v) for v in self.owner_local_face_ids],
            'neighbor_cell_ids': [int(v) for v in self.neighbor_cell_ids],
            'neighbor_local_face_ids': [int(v) for v in self.neighbor_local_face_ids],
            'node_ids': [[int(i) for i in tri] for tri in self.node_ids],
            'normals': [[float(v) for v in n] for n in self.normals],
            'owner_to_neighbor_normal': [float(v) for v in self.owner_to_neighbor_normal],
            'areas': [float(v) for v in self.areas],
            'area': total_area,
            'face_count': len(self.node_ids),
            'matched_face_count': len(self.owner_cell_ids),
            'unmatched_face_count': len(self.unmatched_node_faces),
            'unmatched_node_faces': [[int(i) for i in tri] for tri in self.unmatched_node_faces[:50]],
            'normal_consistency_score': float(self.normal_consistency_score),
            'solver_ready': bool(self.owner_cell_ids),
            'requires_neighbor_for_interface': self.side == 'internal' and not self.neighbor_cell_ids,
            'metadata': dict(self.metadata),
        }


class FaceSetExtractor:
    """Convert Gmsh physical surfaces into solver-ready boundary/internal face sets."""

    def _build_face_lookup(self, mesh: Any, volume_rows_by_pid: dict[int, dict[str, Any]]) -> tuple[dict[tuple[int, int, int], list[tuple[int, int, str]]], int]:
        face_lookup: dict[tuple[int, int, int], list[tuple[int, int, str]]] = {}
        volume_cell_offset = 0
        for block_index, cb in enumerate(getattr(mesh, 'cells', []) or []):
            ctype = str(getattr(cb, 'type', '') or '')
            data = getattr(cb, 'data', None)
            if ctype != 'tetra' or data is None:
                continue
            arr = np.asarray(data, dtype=np.int64)
            phys = _cell_data_array(mesh, 'gmsh:physical', block_index, ctype, arr.shape[0], default=0)
            for local_cell, tet in enumerate(arr):
                region = str(volume_rows_by_pid.get(int(phys[local_cell]), {}).get('region_name') or '')
                global_cell = volume_cell_offset + int(local_cell)
                for local_face, loc in enumerate(TET_FACES):
                    tri = tuple(int(tet[i]) for i in loc)
                    face_lookup.setdefault(tuple(sorted(tri)), []).append((global_cell, local_face, region))
            volume_cell_offset += int(arr.shape[0])
        return face_lookup, volume_cell_offset

    def extract_from_meshio(self, mesh: Any, occ_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = dict(occ_meta or {})
        points = np.asarray(getattr(mesh, 'points', np.zeros((0, 3)))[:, :3], dtype=float)
        _, surface_names = _physical_maps(mesh)
        surface_rows_by_pid = {int(row.get('physical_id')): dict(row) for row in list(meta.get('physical_surface_rows', []) or []) if isinstance(row, dict) and row.get('physical_id') is not None}
        volume_rows_by_pid = {int(row.get('physical_id')): dict(row) for row in list(meta.get('physical_volume_rows', []) or []) if isinstance(row, dict) and row.get('physical_id') is not None}
        face_lookup, _ = self._build_face_lookup(mesh, volume_rows_by_pid)
        groups: dict[int, dict[str, Any]] = {}
        for block_index, cb in enumerate(getattr(mesh, 'cells', []) or []):
            ctype = str(getattr(cb, 'type', '') or '')
            data = getattr(cb, 'data', None)
            if ctype not in {'triangle', 'triangle6'} or data is None:
                continue
            arr = np.asarray(data, dtype=np.int64)[:, :3]
            phys = _cell_data_array(mesh, 'gmsh:physical', block_index, ctype, arr.shape[0], default=0)
            geom = _cell_data_array(mesh, 'gmsh:geometrical', block_index, ctype, arr.shape[0], default=0)
            for tri, pid, gid in zip(arr, phys, geom):
                pid_int = int(pid)
                row = surface_rows_by_pid.get(pid_int, {})
                group = groups.setdefault(pid_int, {
                    'name': str(row.get('face_set_name') or surface_names.get(pid_int, f'face_set_{pid_int}')),
                    'physical_name': str(row.get('physical_name') or surface_names.get(pid_int, '')),
                    'surface_role': str(row.get('surface_role') or 'boundary_surface'),
                    'occ_surface_tag': int(row.get('occ_surface_tag') or gid or 0),
                    'adjacent_region': str(row.get('region_name') or row.get('source_block') or ''),
                    'owner_region': '',
                    'neighbor_region': '',
                    'owner_cell_ids': [],
                    'owner_local_face_ids': [],
                    'neighbor_cell_ids': [],
                    'neighbor_local_face_ids': [],
                    'node_ids': [],
                    'normals': [],
                    'areas': [],
                    'unmatched_node_faces': [],
                    'normal_dots': [],
                    'metadata': {'topology_entity_id': row.get('topology_entity_id', ''), 'protected_surface': row.get('protected_surface', '')},
                })
                tri_tuple = tuple(int(i) for i in tri[:3])
                area, normal = _tri_area_normal(points, tri_tuple)
                found = face_lookup.get(tuple(sorted(tri_tuple)), [])
                if not found:
                    group['unmatched_node_faces'].append(tri_tuple)
                else:
                    owner = found[0]
                    group['owner_cell_ids'].append(int(owner[0]))
                    group['owner_local_face_ids'].append(int(owner[1]))
                    if owner[2] and not group['owner_region']:
                        group['owner_region'] = owner[2]
                    if len(found) > 1:
                        neighbor = found[1]
                        group['neighbor_cell_ids'].append(int(neighbor[0]))
                        group['neighbor_local_face_ids'].append(int(neighbor[1]))
                        if neighbor[2] and not group['neighbor_region']:
                            group['neighbor_region'] = neighbor[2]
                    # Store a simple consistency proxy. Exact outwardness requires
                    # OCC normals; this still catches random triangle orientation.
                    if group['normals']:
                        group['normal_dots'].append(_normal_dot(group['normals'][0], normal))
                group['node_ids'].append(tri_tuple)
                group['normals'].append(normal)
                group['areas'].append(float(area))
        face_sets: list[dict[str, Any]] = []
        for pid, payload in sorted(groups.items(), key=lambda kv: kv[0]):
            owner_region = str(payload.get('owner_region') or payload.get('adjacent_region') or '')
            neighbor_region = str(payload.get('neighbor_region') or '')
            normal_dots = [float(v) for v in payload.get('normal_dots', []) if v != 0.0]
            normal_score = float(sum(1 for v in normal_dots if v >= -0.2) / len(normal_dots)) if normal_dots else 1.0
            side = 'internal' if neighbor_region else 'boundary'
            normals = payload.get('normals', []) or []
            avg_normal = tuple(float(v) for v in (np.mean(np.asarray(normals, dtype=float), axis=0) if normals else np.zeros(3)))
            face_sets.append(FaceSet(
                physical_id=int(pid),
                name=str(payload.get('name') or f'face_set_{pid}'),
                physical_name=str(payload.get('physical_name') or ''),
                surface_role=str(payload.get('surface_role') or 'boundary_surface'),
                occ_surface_tag=int(payload.get('occ_surface_tag') or 0),
                adjacent_region=owner_region,
                owner_region=owner_region,
                neighbor_region=neighbor_region,
                side=side,
                owner_cell_ids=tuple(int(v) for v in payload.get('owner_cell_ids', []) or []),
                owner_local_face_ids=tuple(int(v) for v in payload.get('owner_local_face_ids', []) or []),
                neighbor_cell_ids=tuple(int(v) for v in payload.get('neighbor_cell_ids', []) or []),
                neighbor_local_face_ids=tuple(int(v) for v in payload.get('neighbor_local_face_ids', []) or []),
                node_ids=tuple(tuple(int(i) for i in tri) for tri in payload.get('node_ids', []) or []),
                normals=tuple(tuple(float(x) for x in n) for n in payload.get('normals', []) or []),
                owner_to_neighbor_normal=avg_normal,
                areas=tuple(float(v) for v in payload.get('areas', []) or []),
                unmatched_node_faces=tuple(tuple(int(i) for i in tri) for tri in payload.get('unmatched_node_faces', []) or []),
                normal_consistency_score=normal_score,
                metadata=dict(payload.get('metadata', {}) or {}),
            ).to_dict())
        unmatched = sum(int(row.get('unmatched_face_count', 0) or 0) for row in face_sets)
        matched = sum(int(row.get('matched_face_count', 0) or 0) for row in face_sets)
        internal = sum(1 for row in face_sets if row.get('side') == 'internal')
        normal_bad = sum(1 for row in face_sets if float(row.get('normal_consistency_score', 1.0) or 1.0) < 0.75)
        return {
            'contract': 'solver_ready_face_sets_v2',
            'face_sets': face_sets,
            'summary': {
                'face_set_count': len(face_sets),
                'boundary_face_set_count': len(face_sets) - internal,
                'internal_face_set_count': internal,
                'matched_boundary_face_count': matched,
                'unmatched_boundary_face_count': unmatched,
                'normal_inconsistent_face_set_count': normal_bad,
                'solver_ready_face_set_count': sum(1 for row in face_sets if row.get('solver_ready')),
            },
        }


__all__ = ['FaceSet', 'FaceSetExtractor']
