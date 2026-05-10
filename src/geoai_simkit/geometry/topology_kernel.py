from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

Point3 = tuple[float, float, float]


def _as_point3(value: Sequence[Any]) -> Point3:
    vals = list(value or [])[:3]
    if len(vals) != 3:
        raise ValueError('A 3D point must contain exactly three numeric values.')
    return (float(vals[0]), float(vals[1]), float(vals[2]))


def _slug(value: str, *, fallback: str = 'entity') -> str:
    text = ''.join(ch if ch.isalnum() or ch in {'_', '-', ':'} else '_' for ch in str(value or '').strip())
    text = '_'.join(part for part in text.split('_') if part)
    return text or fallback


def _vsub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vadd(a: Point3, b: Point3) -> Point3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vmul(a: Point3, s: float) -> Point3:
    return (a[0] * float(s), a[1] * float(s), a[2] * float(s))


def _dot(a: Point3, b: Point3) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _cross(a: Point3, b: Point3) -> Point3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Point3) -> float:
    return float((_dot(a, a)) ** 0.5)


def _normalize(a: Point3, *, fallback: Point3 = (0.0, 0.0, 1.0)) -> Point3:
    n = _norm(a)
    if n <= 1.0e-14:
        return fallback
    return (a[0] / n, a[1] / n, a[2] / n)


def _centroid(points: Sequence[Point3]) -> Point3:
    if not points:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / float(len(points))
    return (
        sum(p[0] for p in points) * inv,
        sum(p[1] for p in points) * inv,
        sum(p[2] for p in points) * inv,
    )


def polygon_area_3d(points: Sequence[Point3]) -> float:
    """Return the area of a planar 3D polygon using Newell's method."""
    pts = list(points or [])
    if len(pts) < 3:
        return 0.0
    acc = (0.0, 0.0, 0.0)
    for i, p0 in enumerate(pts):
        p1 = pts[(i + 1) % len(pts)]
        acc = _vadd(acc, _cross(p0, p1))
    return 0.5 * _norm(acc)


def polygon_normal(points: Sequence[Point3], *, fallback: Point3 = (0.0, 0.0, 1.0)) -> Point3:
    pts = list(points or [])
    if len(pts) < 3:
        return fallback
    acc = (0.0, 0.0, 0.0)
    for i, p0 in enumerate(pts):
        p1 = pts[(i + 1) % len(pts)]
        acc = _vadd(acc, _cross(p0, p1))
    return _normalize(acc, fallback=fallback)


def quantized_point(point: Sequence[Any], *, ndigits: int = 9) -> Point3:
    p = _as_point3(point)
    return (round(p[0], ndigits), round(p[1], ndigits), round(p[2], ndigits))


@dataclass(frozen=True, slots=True)
class GeoVertex:
    id: str
    xyz: Point3
    source: str = 'topology'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'xyz': [float(v) for v in self.xyz], 'source': self.source, 'metadata': dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class GeoEdge:
    id: str
    vertex_ids: tuple[str, str]
    solid_id: str = ''
    face_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'vertex_ids': list(self.vertex_ids),
            'solid_id': self.solid_id,
            'face_ids': list(self.face_ids),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GeoFace:
    id: str
    solid_id: str
    vertex_ids: tuple[str, ...]
    normal: Point3
    area: float
    centroid: Point3
    role: str = 'boundary'
    boundary_kind: str = 'external'
    label: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'solid_id': self.solid_id,
            'vertex_ids': list(self.vertex_ids),
            'normal': [float(v) for v in self.normal],
            'area': float(self.area),
            'centroid': [float(v) for v in self.centroid],
            'role': self.role,
            'boundary_kind': self.boundary_kind,
            'label': self.label,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GeoSolid:
    id: str
    name: str
    face_ids: tuple[str, ...]
    role: str = 'soil'
    material_name: str | None = None
    source_block: str | None = None
    bounds: tuple[float, float, float, float, float, float] | None = None
    volume: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'face_ids': list(self.face_ids),
            'role': self.role,
            'material_name': self.material_name,
            'source_block': self.source_block,
            'bounds': None if self.bounds is None else [float(v) for v in self.bounds],
            'volume': float(self.volume),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NamedSelection:
    name: str
    kind: str
    entity_ids: tuple[str, ...]
    role: str = ''
    source: str = 'geometry'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'kind': self.kind,
            'entity_ids': list(self.entity_ids),
            'entity_count': len(self.entity_ids),
            'role': self.role,
            'source': self.source,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class TopologyDocument:
    vertices: tuple[GeoVertex, ...] = ()
    edges: tuple[GeoEdge, ...] = ()
    faces: tuple[GeoFace, ...] = ()
    solids: tuple[GeoSolid, ...] = ()
    named_selections: tuple[NamedSelection, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        role_counts: dict[str, int] = {}
        for solid in self.solids:
            role_counts[solid.role] = role_counts.get(solid.role, 0) + 1
        face_kind_counts: dict[str, int] = {}
        for face in self.faces:
            face_kind_counts[face.boundary_kind] = face_kind_counts.get(face.boundary_kind, 0) + 1
        selection_kind_counts: dict[str, int] = {}
        for sel in self.named_selections:
            selection_kind_counts[sel.kind] = selection_kind_counts.get(sel.kind, 0) + 1
        return {
            'vertices': [item.to_dict() for item in self.vertices],
            'edges': [item.to_dict() for item in self.edges],
            'faces': [item.to_dict() for item in self.faces],
            'solids': [item.to_dict() for item in self.solids],
            'named_selections': [item.to_dict() for item in self.named_selections],
            'issues': [dict(issue) for issue in self.issues],
            'summary': {
                'vertex_count': len(self.vertices),
                'edge_count': len(self.edges),
                'face_count': len(self.faces),
                'solid_count': len(self.solids),
                'named_selection_count': len(self.named_selections),
                'issue_count': len(self.issues),
                'role_counts': role_counts,
                'face_kind_counts': face_kind_counts,
                'selection_kind_counts': selection_kind_counts,
                'kernel': 'editable_block_topology_v1',
            },
            'metadata': dict(self.metadata),
        }


_FACE_VERTEX_INDEX = {
    'xmin': (0, 3, 7, 4),
    'xmax': (1, 5, 6, 2),
    'ymin': (0, 4, 5, 1),
    'ymax': (3, 2, 6, 7),
    'zmin': (0, 1, 2, 3),
    'zmax': (4, 7, 6, 5),
}
_FACE_NORMALS: dict[str, Point3] = {
    'xmin': (-1.0, 0.0, 0.0),
    'xmax': (1.0, 0.0, 0.0),
    'ymin': (0.0, -1.0, 0.0),
    'ymax': (0.0, 1.0, 0.0),
    'zmin': (0.0, 0.0, -1.0),
    'zmax': (0.0, 0.0, 1.0),
}


def box_vertices_from_bounds(bounds: Iterable[Any]) -> tuple[Point3, ...]:
    vals = [float(v) for v in list(bounds or [])[:6]]
    if len(vals) != 6:
        raise ValueError('Box bounds must contain six values: xmin, xmax, ymin, ymax, zmin, zmax.')
    xmin, xmax, ymin, ymax, zmin, zmax = vals
    xmin, xmax = min(xmin, xmax), max(xmin, xmax)
    ymin, ymax = min(ymin, ymax), max(ymin, ymax)
    zmin, zmax = min(zmin, zmax), max(zmin, zmax)
    return (
        (xmin, ymin, zmin),
        (xmax, ymin, zmin),
        (xmax, ymax, zmin),
        (xmin, ymax, zmin),
        (xmin, ymin, zmax),
        (xmax, ymin, zmax),
        (xmax, ymax, zmax),
        (xmin, ymax, zmax),
    )


def _volume_from_bounds(bounds: Iterable[Any]) -> float:
    xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in list(bounds or [])[:6]]
    return max(0.0, xmax - xmin) * max(0.0, ymax - ymin) * max(0.0, zmax - zmin)


def _block_name(row: dict[str, Any], index: int) -> str:
    return _slug(str(row.get('name') or row.get('region_name') or f'block_{index:03d}'), fallback=f'block_{index:03d}')


def _block_bounds(row: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    vals = [float(v) for v in list(row.get('bounds') or row.get('box_bounds') or row.get('extent') or [])[:6]]
    if len(vals) != 6:
        raise ValueError(f"Block {row.get('name')!r} does not define six bounds values.")
    xmin, xmax, ymin, ymax, zmin, zmax = vals
    return (min(xmin, xmax), max(xmin, xmax), min(ymin, ymax), max(ymin, ymax), min(zmin, zmax), max(zmin, zmax))


def build_topology_from_editable_blocks(
    blocks: Iterable[dict[str, Any]],
    *,
    include_face_named_selections: bool = True,
    include_role_named_selections: bool = True,
) -> TopologyDocument:
    """Build a dependency-light topology document from editable block boxes.

    The document makes block/face/edge identities explicit before meshing. It is
    intentionally conservative: each block keeps its own boundary vertices, so a
    shared boundary can later become either merged continuity, a duplicate-node
    interface, or a contact/interface element depending on mesh policy.
    """
    vertices: list[GeoVertex] = []
    edges: list[GeoEdge] = []
    faces: list[GeoFace] = []
    solids: list[GeoSolid] = []
    selections: list[NamedSelection] = []
    issues: list[dict[str, Any]] = []
    role_to_solids: dict[str, list[str]] = {}

    for index, raw in enumerate(list(blocks or []), start=1):
        if not isinstance(raw, dict):
            continue
        try:
            name = _block_name(raw, index)
            bounds = _block_bounds(raw)
            box_pts = box_vertices_from_bounds(bounds)
        except Exception as exc:
            issues.append({'id': f'topology.block_{index:03d}.invalid', 'severity': 'warning', 'message': str(exc), 'target': 'geometry_topology', 'action': 'Fix editable block bounds.'})
            continue
        role = str(raw.get('role') or 'soil')
        material_name = None if raw.get('material_name') in {None, ''} else str(raw.get('material_name'))
        solid_id = f'solid:{name}'
        local_vids: list[str] = []
        for vidx, xyz in enumerate(box_pts):
            vid = f'vertex:{name}:{vidx:02d}'
            local_vids.append(vid)
            vertices.append(GeoVertex(id=vid, xyz=quantized_point(xyz), source='editable_block', metadata={'block': name, 'local_index': vidx}))
        face_ids: list[str] = []
        edge_face_lookup: dict[tuple[str, str], list[str]] = {}
        for face_label, idxs in _FACE_VERTEX_INDEX.items():
            fids = tuple(local_vids[i] for i in idxs)
            pts = tuple(box_pts[i] for i in idxs)
            fid = f'face:{name}:{face_label}'
            face_ids.append(fid)
            faces.append(GeoFace(
                id=fid,
                solid_id=solid_id,
                vertex_ids=fids,
                normal=_FACE_NORMALS[face_label],
                area=polygon_area_3d(pts),
                centroid=_centroid(pts),
                role=role,
                boundary_kind='block_boundary',
                label=face_label,
                metadata={'block': name, 'region_name': raw.get('region_name') or name, 'bounds': list(bounds)},
            ))
            if include_face_named_selections:
                selections.append(NamedSelection(
                    name=f'{name}:{face_label}',
                    kind='face',
                    entity_ids=(fid,),
                    role=f'{role}_face',
                    source='editable_block_face',
                    metadata={'block': name, 'face_label': face_label, 'normal': list(_FACE_NORMALS[face_label])},
                ))
            for j, v0 in enumerate(fids):
                v1 = fids[(j + 1) % len(fids)]
                edge_key = tuple(sorted((v0, v1)))
                edge_face_lookup.setdefault(edge_key, []).append(fid)
        for eidx, (edge_key, face_refs) in enumerate(sorted(edge_face_lookup.items()), start=1):
            edges.append(GeoEdge(
                id=f'edge:{name}:{eidx:02d}',
                vertex_ids=(edge_key[0], edge_key[1]),
                solid_id=solid_id,
                face_ids=tuple(face_refs),
                metadata={'block': name},
            ))
        solid = GeoSolid(
            id=solid_id,
            name=name,
            face_ids=tuple(face_ids),
            role=role,
            material_name=material_name,
            source_block=name,
            bounds=bounds,
            volume=_volume_from_bounds(bounds),
            metadata=dict(raw.get('metadata', {}) or {}),
        )
        solids.append(solid)
        selections.append(NamedSelection(name=name, kind='solid', entity_ids=(solid_id,), role=role, source='editable_block', metadata={'block': name}))
        role_to_solids.setdefault(role, []).append(solid_id)

    if include_role_named_selections:
        for role, ids in sorted(role_to_solids.items()):
            selections.append(NamedSelection(name=f'role:{role}', kind='solid', entity_ids=tuple(ids), role=role, source='role_index', metadata={'role': role}))

    return TopologyDocument(
        vertices=tuple(vertices),
        edges=tuple(edges),
        faces=tuple(faces),
        solids=tuple(solids),
        named_selections=tuple(selections),
        issues=tuple(issues),
        metadata={'source': 'editable_blocks', 'topology_contract': 'geometry_topology_v1'},
    )


def build_topology_payload_from_blocks(blocks: Iterable[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    return build_topology_from_editable_blocks(blocks, **kwargs).to_dict()


__all__ = [
    'GeoEdge',
    'GeoFace',
    'GeoSolid',
    'GeoVertex',
    'NamedSelection',
    'Point3',
    'TopologyDocument',
    'box_vertices_from_bounds',
    'build_topology_from_editable_blocks',
    'build_topology_payload_from_blocks',
    'polygon_area_3d',
    'polygon_normal',
    'quantized_point',
]
