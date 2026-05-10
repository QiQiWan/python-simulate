from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

Point3 = tuple[float, float, float]
Bounds6 = tuple[float, float, float, float, float, float]


def _as_float_list(values: Iterable[Any] | None, n: int, default: float = 0.0) -> list[float]:
    out = [float(default)] * n
    for i, value in enumerate(list(values or [])[:n]):
        out[i] = float(value)
    return out


def _bounds(values: Iterable[Any] | None) -> Bounds6:
    raw = _as_float_list(values, 6)
    xmin, xmax, ymin, ymax, zmin, zmax = raw
    if xmax < xmin:
        xmin, xmax = xmax, xmin
    if ymax < ymin:
        ymin, ymax = ymax, ymin
    if zmax < zmin:
        zmin, zmax = zmax, zmin
    return (xmin, xmax, ymin, ymax, zmin, zmax)


def _center(bounds: Sequence[float]) -> Point3:
    xmin, xmax, ymin, ymax, zmin, zmax = _bounds(bounds)
    return (0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax))


def _extent(bounds: Sequence[float]) -> Point3:
    xmin, xmax, ymin, ymax, zmin, zmax = _bounds(bounds)
    return (max(0.0, xmax - xmin), max(0.0, ymax - ymin), max(0.0, zmax - zmin))


def _bbox_area(bounds: Sequence[float]) -> float:
    dx, dy, dz = _extent(bounds)
    dims = sorted([dx, dy, dz], reverse=True)
    return float(dims[0] * dims[1])


def _bbox_volume(bounds: Sequence[float]) -> float:
    dx, dy, dz = _extent(bounds)
    return float(dx * dy * dz)


def _normal_from_bounds(bounds: Sequence[float]) -> Point3:
    dx, dy, dz = _extent(bounds)
    eps = max(max(dx, dy, dz) * 1.0e-6, 1.0e-9)
    if dx <= eps:
        return (1.0, 0.0, 0.0)
    if dy <= eps:
        return (0.0, 1.0, 0.0)
    if dz <= eps:
        return (0.0, 0.0, 1.0)
    # Fragmented curved/oblique surface fallback: normal is unknown until exact OCC
    # topology is queried; keep a deterministic placeholder for GUI contracts.
    return (0.0, 0.0, 0.0)


def _slug(text: str, fallback: str = 'entity') -> str:
    clean = ''.join(ch if ch.isalnum() or ch in {'_', '-', ':', '.'} else '_' for ch in str(text or '').strip())
    clean = '_'.join(part for part in clean.split('_') if part)
    return clean or fallback


def _surface_volume_adjacency(surface_bounds: Bounds6 | None, volumes: Sequence[Any], region_hint: str = "") -> tuple[str, ...]:
    if surface_bounds is None:
        return tuple([v.id for v in volumes if region_hint and getattr(v, "region_name", "") == region_hint][:1])
    sxmin, sxmax, symin, symax, szmin, szmax = surface_bounds
    eps = max(max(abs(sxmax - sxmin), abs(symax - symin), abs(szmax - szmin), 1.0) * 1.0e-6, 1.0e-8)
    adjacent: list[str] = []
    for vol in volumes:
        vbounds = getattr(vol, "bounds", None)
        if vbounds is None:
            if region_hint and getattr(vol, "region_name", "") == region_hint:
                adjacent.append(vol.id)
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = vbounds
        overlap = not (sxmax < xmin - eps or sxmin > xmax + eps or symax < ymin - eps or symin > ymax + eps or szmax < zmin - eps or szmin > zmax + eps)
        if not overlap:
            continue
        touches = (abs(sxmin - xmin) <= eps or abs(sxmax - xmax) <= eps or abs(symin - ymin) <= eps or abs(symax - ymax) <= eps or abs(szmin - zmin) <= eps or abs(szmax - zmax) <= eps)
        inside = sxmin >= xmin - eps and sxmax <= xmax + eps and symin >= ymin - eps and symax <= ymax + eps and szmin >= zmin - eps and szmax <= zmax + eps
        if touches or inside or (region_hint and getattr(vol, "region_name", "") == region_hint):
            adjacent.append(vol.id)
    return tuple(dict.fromkeys(adjacent))


@dataclass(frozen=True, slots=True)
class BRepVolume:
    id: str
    occ_tag: int
    physical_id: int | None
    region_name: str
    source_block: str
    role: str = ''
    material_name: str | None = None
    bounds: Bounds6 | None = None
    center: Point3 | None = None
    volume_estimate: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': 'solid',
            'occ_dim': 3,
            'occ_tag': int(self.occ_tag),
            'physical_id': self.physical_id,
            'region_name': self.region_name,
            'source_block': self.source_block,
            'role': self.role,
            'material_name': self.material_name,
            'bounds': None if self.bounds is None else [float(v) for v in self.bounds],
            'center': None if self.center is None else [float(v) for v in self.center],
            'volume_estimate': float(self.volume_estimate),
            'editable': True,
            'edit_policy': 'edit_source_entity_then_remesh',
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BRepSurface:
    id: str
    occ_tag: int
    physical_id: int | None
    face_set_name: str
    source_block: str
    region_name: str
    surface_role: str = 'boundary_surface'
    protected_surface: str = ''
    bounds: Bounds6 | None = None
    center: Point3 | None = None
    normal: Point3 = (0.0, 0.0, 0.0)
    area_estimate: float = 0.0
    adjacent_volume_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': 'face',
            'occ_dim': 2,
            'occ_tag': int(self.occ_tag),
            'physical_id': self.physical_id,
            'face_set_name': self.face_set_name,
            'source_block': self.source_block,
            'region_name': self.region_name,
            'surface_role': self.surface_role,
            'protected_surface': self.protected_surface,
            'bounds': None if self.bounds is None else [float(v) for v in self.bounds],
            'center': None if self.center is None else [float(v) for v in self.center],
            'normal': [float(v) for v in self.normal],
            'area_estimate': float(self.area_estimate),
            'adjacent_volume_ids': list(self.adjacent_volume_ids),
            'editable': True,
            'edit_policy': 'edit_source_entity_then_remesh',
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BRepEdge:
    id: str
    occ_tag: int
    source_surface_id: str
    bounds: Bounds6 | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': 'edge',
            'occ_dim': 1,
            'occ_tag': int(self.occ_tag),
            'source_surface_id': self.source_surface_id,
            'bounds': None if self.bounds is None else [float(v) for v in self.bounds],
            'editable': True,
            'edit_policy': 'edit_source_entity_then_remesh',
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BRepDocument:
    volumes: tuple[BRepVolume, ...] = ()
    surfaces: tuple[BRepSurface, ...] = ()
    edges: tuple[BRepEdge, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        role_counts: dict[str, int] = {}
        surface_role_counts: dict[str, int] = {}
        for vol in self.volumes:
            role_counts[vol.role or ''] = role_counts.get(vol.role or '', 0) + 1
        for surf in self.surfaces:
            surface_role_counts[surf.surface_role] = surface_role_counts.get(surf.surface_role, 0) + 1
        return {
            'contract': 'brep_document_v2',
            'volumes': [v.to_dict() for v in self.volumes],
            'surfaces': [s.to_dict() for s in self.surfaces],
            'edges': [e.to_dict() for e in self.edges],
            'issues': [dict(i) for i in self.issues],
            'summary': {
                'volume_count': len(self.volumes),
                'surface_count': len(self.surfaces),
                'edge_count': len(self.edges),
                'issue_count': len(self.issues),
                'role_counts': role_counts,
                'surface_role_counts': surface_role_counts,
                'editable_policy': 'source_brep_entity_edit_requires_remesh',
                'topological_naming': str(self.metadata.get('topological_naming', 'feature_occ_dimtag_semantic_v2')),
            },
            'metadata': dict(self.metadata),
        }


def build_brep_document_from_occ_meta(occ_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict(occ_meta or {})
    volume_rows = [dict(row) for row in list(meta.get('physical_volume_rows', []) or []) if isinstance(row, dict)]
    surface_rows = [dict(row) for row in list(meta.get('physical_surface_rows', []) or []) if isinstance(row, dict)]
    volumes: list[BRepVolume] = []
    for row in volume_rows:
        occ_tag = int(row.get('occ_volume_tag', row.get('occ_tag', 0)) or 0)
        region = str(row.get('region_name') or row.get('source_block') or f'occ_volume_{occ_tag}')
        bounds = _bounds(row.get('bounds') or ()) if row.get('bounds') else None
        center = tuple(float(v) for v in list(row.get('center') or _center(bounds or (0, 0, 0, 0, 0, 0)))[:3])  # type: ignore[assignment]
        entity_id = f'solid:{_slug(region)}:occ_3_{occ_tag}'
        volumes.append(BRepVolume(
            id=entity_id,
            occ_tag=occ_tag,
            physical_id=None if row.get('physical_id') in {None, ''} else int(row.get('physical_id')),
            region_name=region,
            source_block=str(row.get('source_block') or region),
            role=str(row.get('role') or ''),
            material_name=None if row.get('material_name') in {None, ''} else str(row.get('material_name')),
            bounds=bounds,
            center=center,
            volume_estimate=float(row.get('volume') or row.get('volume_bbox') or (_bbox_volume(bounds) if bounds else 0.0)),
            metadata={'physical_name': row.get('physical_name', ''), **dict(row.get('metadata', {}) or {})},
        ))
    volume_by_region = {v.region_name: v.id for v in volumes}
    surfaces: list[BRepSurface] = []
    edges: list[BRepEdge] = []
    for row in surface_rows:
        occ_tag = int(row.get('occ_surface_tag', row.get('occ_tag', 0)) or 0)
        name = str(row.get('face_set_name') or row.get('name') or f'occ_surface_{occ_tag}')
        region = str(row.get('region_name') or row.get('source_block') or '')
        bounds = _bounds(row.get('bounds') or ()) if row.get('bounds') else None
        center = tuple(float(v) for v in list(row.get('center') or _center(bounds or (0, 0, 0, 0, 0, 0)))[:3])  # type: ignore[assignment]
        role = str(row.get('surface_role') or 'boundary_surface')
        protected = str(row.get('protected_surface') or '')
        entity_id = str(row.get('topology_entity_id') or '')
        if not entity_id:
            prefix = 'protected_surface' if protected else 'face_set'
            entity_id = f'{prefix}:{_slug(name)}:occ_2_{occ_tag}'
        surfaces.append(BRepSurface(
            id=entity_id,
            occ_tag=occ_tag,
            physical_id=None if row.get('physical_id') in {None, ''} else int(row.get('physical_id')),
            face_set_name=name,
            source_block=str(row.get('source_block') or region),
            region_name=region,
            surface_role=role,
            protected_surface=protected,
            bounds=bounds,
            center=center,
            normal=_normal_from_bounds(bounds or (0, 0, 0, 0, 0, 0)),
            area_estimate=float(row.get('area') or row.get('area_estimate') or (_bbox_area(bounds) if bounds else 0.0)),
            adjacent_volume_ids=_surface_volume_adjacency(bounds, volumes, region),
            metadata={'physical_name': row.get('physical_name', ''), **dict(row.get('metadata', {}) or {})},
        ))
        if bounds is not None:
            # Lightweight editable edge placeholders are derived from surface bounds.
            # Exact OCC curve tags can replace these when the host queries OCC curves.
            for i in range(4):
                edges.append(BRepEdge(
                    id=f'edge:{_slug(name)}:proxy_{i + 1}:occ_1_{occ_tag}_{i + 1}',
                    occ_tag=0,
                    source_surface_id=entity_id,
                    bounds=bounds,
                    metadata={'proxy': True, 'surface_occ_tag': occ_tag},
                ))
    issues: list[dict[str, Any]] = []
    if not volumes and not surfaces:
        issues.append({'id': 'brep.empty', 'severity': 'info', 'message': 'No OCC physical volume/surface rows were available to build a BRep document.'})
    return BRepDocument(
        volumes=tuple(volumes),
        surfaces=tuple(surfaces),
        edges=tuple(edges),
        issues=tuple(issues),
        metadata={'source_contract': meta.get('contract', ''), 'mesh_contract': meta.get('face_set_contract', ''), 'topological_naming': 'feature_occ_dimtag_semantic_v2', 'adjacency_inference': 'bounds_and_region_hint'},
    ).to_dict()


__all__ = ['BRepDocument', 'BRepEdge', 'BRepSurface', 'BRepVolume', 'build_brep_document_from_occ_meta']
