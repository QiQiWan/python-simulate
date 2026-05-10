from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from geoai_simkit.geometry.editable_blocks import EditableBlock, editable_blocks_to_rows, normalize_editable_blocks
from geoai_simkit.geometry.topology_kernel import Point3, polygon_area_3d


def _as_point3(value: Sequence[Any] | None, *, default: Point3 = (0.0, 0.0, 0.0)) -> Point3:
    if value is None:
        return default
    vals = list(value)[:3]
    if len(vals) != 3:
        raise ValueError('point/normal must contain exactly three values.')
    return (float(vals[0]), float(vals[1]), float(vals[2]))


def _dot(a: Point3, b: Point3) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _sub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(a: Point3) -> float:
    return float((_dot(a, a)) ** 0.5)


def _normalize(a: Point3) -> Point3:
    n = _norm(a)
    if n <= 1.0e-14:
        raise ValueError('Plane normal cannot be zero.')
    return (a[0] / n, a[1] / n, a[2] / n)


def _cross(a: Point3, b: Point3) -> Point3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _center(points: Sequence[Point3]) -> Point3:
    inv = 1.0 / max(len(points), 1)
    return (sum(p[0] for p in points) * inv, sum(p[1] for p in points) * inv, sum(p[2] for p in points) * inv)


def _sort_polygon_on_plane(points: Sequence[Point3], normal: Point3) -> tuple[Point3, ...]:
    pts = list(points)
    if len(pts) <= 2:
        return tuple(pts)
    n = _normalize(normal)
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _normalize(_cross(n, ref))
    v = _cross(n, u)
    c = _center(pts)
    import math
    def angle(p: Point3) -> float:
        r = _sub(p, c)
        return math.atan2(_dot(r, v), _dot(r, u))
    return tuple(sorted(pts, key=angle))


def _dedup_points(points: Iterable[Point3], *, ndigits: int = 9) -> tuple[Point3, ...]:
    out: list[Point3] = []
    seen: set[tuple[float, float, float]] = set()
    for p in points:
        key = (round(float(p[0]), ndigits), round(float(p[1]), ndigits), round(float(p[2]), ndigits))
        if key in seen:
            continue
        seen.add(key)
        out.append((float(key[0]), float(key[1]), float(key[2])))
    return tuple(out)


def _aabb_vertices(bounds: Sequence[Any]) -> tuple[Point3, ...]:
    xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in list(bounds)[:6]]
    return (
        (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
        (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax),
    )


_AABB_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)


@dataclass(frozen=True, slots=True)
class SplitSurface:
    name: str
    target_block: str
    kind: str
    point: Point3
    normal: Point3
    polygon: tuple[Point3, ...] = ()
    area: float = 0.0
    role: str = 'protected_split_face'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'target_block': self.target_block,
            'kind': self.kind,
            'point': [float(v) for v in self.point],
            'normal': [float(v) for v in self.normal],
            'polygon': [[float(v) for v in p] for p in self.polygon],
            'area': float(self.area),
            'role': self.role,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PartitionResult:
    success: bool
    target_block: str
    mode: str
    child_blocks: tuple[dict[str, Any], ...] = ()
    split_surface: SplitSurface | None = None
    named_selections: tuple[dict[str, Any], ...] = ()
    contact_pair_rows: tuple[dict[str, Any], ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'success': bool(self.success),
            'target_block': self.target_block,
            'mode': self.mode,
            'child_blocks': [dict(row) for row in self.child_blocks],
            'split_surface': None if self.split_surface is None else self.split_surface.to_dict(),
            'named_selections': [dict(row) for row in self.named_selections],
            'contact_pair_rows': [dict(row) for row in self.contact_pair_rows],
            'issues': [dict(issue) for issue in self.issues],
            'metadata': dict(self.metadata),
        }


def plane_aabb_intersection_polygon(bounds: Sequence[Any], point: Sequence[Any], normal: Sequence[Any], *, tolerance: float = 1.0e-9) -> tuple[Point3, ...]:
    """Intersect an infinite plane with an AABB and return a sorted polygon.

    This does not split the solid; it gives the exact protected surface that the
    mesh/contact pipeline must preserve. It is enough to support oblique split
    preview, named selections, and later OCC/Gmsh handoff.
    """
    p0 = _as_point3(point)
    n = _normalize(_as_point3(normal, default=(0.0, 0.0, 1.0)))
    verts = _aabb_vertices(bounds)
    hits: list[Point3] = []
    for i0, i1 in _AABB_EDGES:
        a = verts[i0]
        b = verts[i1]
        da = _dot(_sub(a, p0), n)
        db = _dot(_sub(b, p0), n)
        if abs(da) <= tolerance:
            hits.append(a)
        if abs(db) <= tolerance:
            hits.append(b)
        if da * db < -tolerance * tolerance:
            t = da / (da - db)
            hits.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])))
    unique = _dedup_points(hits)
    if len(unique) < 3:
        return ()
    return _sort_polygon_on_plane(unique, n)


def _axis_surface_polygon(block: EditableBlock, axis: str, coordinate: float) -> tuple[Point3, ...]:
    xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
    c = float(coordinate)
    if axis == 'x':
        return ((c, ymin, zmin), (c, ymax, zmin), (c, ymax, zmax), (c, ymin, zmax))
    if axis == 'y':
        return ((xmin, c, zmin), (xmax, c, zmin), (xmax, c, zmax), (xmin, c, zmax))
    return ((xmin, ymin, c), (xmax, ymin, c), (xmax, ymax, c), (xmin, ymax, c))


def partition_editable_block_axis(block: EditableBlock, *, axis: str = 'z', coordinate: float | None = None, name: str | None = None) -> PartitionResult:
    axis_key = str(axis or 'z').strip().lower()
    if axis_key not in {'x', 'y', 'z'}:
        raise ValueError(f'Unsupported split axis: {axis}')
    negative, positive = block.split(axis=axis_key, coordinate=coordinate)
    lohi = {'x': (block.bounds[0], block.bounds[1]), 'y': (block.bounds[2], block.bounds[3]), 'z': (block.bounds[4], block.bounds[5])}[axis_key]
    cut = float(negative.bounds[{'x': 1, 'y': 3, 'z': 5}[axis_key]])
    normal = {'x': (1.0, 0.0, 0.0), 'y': (0.0, 1.0, 0.0), 'z': (0.0, 0.0, 1.0)}[axis_key]
    point = {'x': (cut, 0.0, 0.0), 'y': (0.0, cut, 0.0), 'z': (0.0, 0.0, cut)}[axis_key]
    polygon = _axis_surface_polygon(block, axis_key, cut)
    split_name = str(name or f'{block.name}__{axis_key}_split').strip()
    surface = SplitSurface(
        name=split_name,
        target_block=block.name,
        kind='axis_plane',
        point=point,
        normal=normal,
        polygon=polygon,
        area=polygon_area_3d(polygon),
        metadata={'axis': axis_key, 'coordinate': cut, 'range': list(lohi), 'exact_child_blocks': True},
    )
    contact_pair = {
        'name': f'auto_split_contact:{split_name}',
        'pair_name': f'auto_split_contact:{split_name}',
        'split_name': split_name,
        'region_a': negative.name,
        'region_b': positive.name,
        'slave_region': negative.name,
        'master_region': positive.name,
        'mesh_policy': 'nonconforming_contact',
        'contact_mode': 'contact',
        'source': 'geometry.partition_engine',
        'protected_surface': split_name,
        'total_overlap_area': float(surface.area),
    }
    selections = (
        {'name': f'{split_name}:negative_child', 'kind': 'solid', 'entity_ids': [negative.name], 'source': 'partition_engine'},
        {'name': f'{split_name}:positive_child', 'kind': 'solid', 'entity_ids': [positive.name], 'source': 'partition_engine'},
        {'name': f'{split_name}:protected_face', 'kind': 'face', 'entity_ids': [split_name], 'source': 'partition_engine', 'metadata': {'area': float(surface.area)}},
    )
    return PartitionResult(
        success=True,
        target_block=block.name,
        mode='axis_exact',
        child_blocks=(negative.to_dict(), positive.to_dict()),
        split_surface=surface,
        named_selections=selections,
        contact_pair_rows=(contact_pair,),
        metadata={'replaces_target_block': True, 'axis': axis_key, 'coordinate': cut},
    )


def partition_editable_block_by_plane(block: EditableBlock, *, point: Sequence[Any], normal: Sequence[Any], name: str | None = None) -> PartitionResult:
    p0 = _as_point3(point)
    n = _normalize(_as_point3(normal, default=(0.0, 0.0, 1.0)))
    polygon = plane_aabb_intersection_polygon(block.bounds, p0, n)
    split_name = str(name or f'{block.name}__plane_split').strip()
    surface = SplitSurface(
        name=split_name,
        target_block=block.name,
        kind='oblique_plane',
        point=p0,
        normal=n,
        polygon=polygon,
        area=polygon_area_3d(polygon),
        metadata={'exact_child_blocks': False, 'requires_solid_kernel': True},
    )
    issues = []
    success = bool(polygon)
    if not polygon:
        issues.append({'id': f'partition.{split_name}.plane_no_intersection', 'severity': 'warning', 'message': 'The split plane does not cut the target block.', 'target': block.name, 'action': 'Move the split plane or choose another target block.'})
    else:
        issues.append({'id': f'partition.{split_name}.virtual_plane_split', 'severity': 'info', 'message': 'Oblique split surface is defined as protected topology. Exact child solid generation requires OCC/Gmsh solid kernel.', 'target': block.name, 'action': 'Use axis split for immediate editable block replacement, or route this plane to the OCC meshing backend.'})
    return PartitionResult(
        success=success,
        target_block=block.name,
        mode='plane_virtual',
        child_blocks=(),
        split_surface=surface,
        named_selections=({'name': f'{split_name}:protected_face', 'kind': 'face', 'entity_ids': [split_name], 'source': 'partition_engine', 'metadata': {'area': float(surface.area), 'virtual': True}},),
        contact_pair_rows=(),
        issues=tuple(issues),
        metadata={'replaces_target_block': False, 'requires_solid_kernel': bool(polygon)},
    )



def partition_applied_axis_surface_from_children(
    negative: EditableBlock,
    positive: EditableBlock,
    *,
    axis: str = 'z',
    coordinate: float | None = None,
    parent_name: str | None = None,
    name: str | None = None,
) -> PartitionResult:
    """Reconstruct a protected split surface after the parent block was replaced."""
    axis_key = str(axis or 'z').strip().lower()
    if axis_key not in {'x', 'y', 'z'}:
        raise ValueError(f'Unsupported split axis: {axis}')
    neg_hi = {'x': negative.bounds[1], 'y': negative.bounds[3], 'z': negative.bounds[5]}[axis_key]
    pos_lo = {'x': positive.bounds[0], 'y': positive.bounds[2], 'z': positive.bounds[4]}[axis_key]
    cut = float(coordinate if coordinate is not None else 0.5 * (float(neg_hi) + float(pos_lo)))
    bounds = (
        min(negative.bounds[0], positive.bounds[0]), max(negative.bounds[1], positive.bounds[1]),
        min(negative.bounds[2], positive.bounds[2]), max(negative.bounds[3], positive.bounds[3]),
        min(negative.bounds[4], positive.bounds[4]), max(negative.bounds[5], positive.bounds[5]),
    )
    parent = str(parent_name or negative.metadata.get('split_parent') or positive.metadata.get('split_parent') or 'applied_split')
    dummy = EditableBlock(parent, bounds)
    polygon = _axis_surface_polygon(dummy, axis_key, cut)
    normal = {'x': (1.0, 0.0, 0.0), 'y': (0.0, 1.0, 0.0), 'z': (0.0, 0.0, 1.0)}[axis_key]
    point = {'x': (cut, 0.0, 0.0), 'y': (0.0, cut, 0.0), 'z': (0.0, 0.0, cut)}[axis_key]
    split_name = str(name or f'{parent}__{axis_key}_applied_split').strip()
    surface = SplitSurface(
        name=split_name,
        target_block=parent,
        kind='axis_plane_applied',
        point=point,
        normal=normal,
        polygon=polygon,
        area=polygon_area_3d(polygon),
        metadata={'axis': axis_key, 'coordinate': cut, 'exact_child_blocks': True, 'partition_applied': True, 'child_regions': [negative.name, positive.name]},
    )
    contact_pair = {
        'name': f'auto_split_contact:{split_name}',
        'pair_name': f'auto_split_contact:{split_name}',
        'split_name': split_name,
        'region_a': negative.name,
        'region_b': positive.name,
        'slave_region': negative.name,
        'master_region': positive.name,
        'mesh_policy': 'nonconforming_contact',
        'contact_mode': 'contact',
        'source': 'geometry.partition_engine.applied_split',
        'protected_surface': split_name,
        'total_overlap_area': float(surface.area),
    }
    return PartitionResult(
        success=True,
        target_block=parent,
        mode='axis_applied',
        child_blocks=(negative.to_dict(), positive.to_dict()),
        split_surface=surface,
        named_selections=(
            {'name': f'{split_name}:negative_child', 'kind': 'solid', 'entity_ids': [negative.name], 'source': 'partition_engine.applied_split'},
            {'name': f'{split_name}:positive_child', 'kind': 'solid', 'entity_ids': [positive.name], 'source': 'partition_engine.applied_split'},
            {'name': f'{split_name}:protected_face', 'kind': 'face', 'entity_ids': [split_name], 'source': 'partition_engine.applied_split', 'metadata': {'area': float(surface.area)}},
        ),
        contact_pair_rows=(contact_pair,),
        metadata={'replaces_target_block': False, 'partition_applied': True, 'axis': axis_key, 'coordinate': cut},
    )


def partition_editable_block_by_polyline_extrusion(
    block: EditableBlock,
    *,
    polyline: Sequence[Sequence[Any]],
    z_min: float | None = None,
    z_max: float | None = None,
    name: str | None = None,
) -> PartitionResult:
    """Define a vertical polyline-extruded protected split surface."""
    points: list[Point3] = []
    for raw in list(polyline or []):
        vals = list(raw)
        if len(vals) < 2:
            continue
        z = float(vals[2]) if len(vals) >= 3 else float(block.bounds[4])
        points.append((float(vals[0]), float(vals[1]), z))
    split_name = str(name or f'{block.name}__polyline_split').strip()
    if len(points) < 2:
        surface = SplitSurface(split_name, block.name, 'polyline_extrusion', block.center, (0.0, 0.0, 1.0), (), 0.0, metadata={'panel_count': 0, 'requires_solid_kernel': True})
        return PartitionResult(False, block.name, 'polyline_virtual', split_surface=surface, issues=({'id': f'partition.{split_name}.polyline_too_short', 'severity': 'warning', 'message': 'Polyline extrusion split requires at least two points.', 'target': block.name, 'action': 'Draw at least two points.'},), metadata={'requires_solid_kernel': True})
    z0 = float(block.bounds[4] if z_min is None else z_min)
    z1 = float(block.bounds[5] if z_max is None else z_max)
    panels: list[list[list[float]]] = []
    total_area = 0.0
    for a, b in zip(points[:-1], points[1:]):
        panel = ((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1))
        panels.append([[float(v) for v in p] for p in panel])
        total_area += polygon_area_3d(panel)
    surface = SplitSurface(
        name=split_name,
        target_block=block.name,
        kind='polyline_extrusion',
        point=(points[0][0], points[0][1], z0),
        normal=(0.0, 0.0, 1.0),
        polygon=(),
        area=total_area,
        metadata={'polyline': [[float(v) for v in p] for p in points], 'z_min': z0, 'z_max': z1, 'panel_polygons': panels, 'panel_count': len(panels), 'requires_solid_kernel': True, 'occ_operation': 'fragment_volume_by_extruded_segment_faces'},
    )
    return PartitionResult(
        success=True,
        target_block=block.name,
        mode='polyline_virtual',
        split_surface=surface,
        named_selections=({'name': f'{split_name}:protected_faces', 'kind': 'face', 'entity_ids': [split_name], 'source': 'partition_engine.polyline_extrusion', 'metadata': {'area': float(total_area), 'panel_count': len(panels), 'virtual': True}},),
        issues=({'id': f'partition.{split_name}.occ_polyline_ready', 'severity': 'info', 'message': 'Polyline extrusion split is stored as protected panels and can be executed by the Gmsh OCC partition backend.', 'target': block.name, 'action': 'Use OCC meshing backend for exact solid partition, or keep as nonconforming protected interface.'},),
        metadata={'replaces_target_block': False, 'requires_solid_kernel': True, 'panel_count': len(panels)},
    )

def apply_axis_partition_to_blocks(
    blocks: Iterable[dict[str, Any]],
    target_block: str,
    *,
    axis: str = 'z',
    coordinate: float | None = None,
    split_name: str | None = None,
) -> tuple[list[dict[str, Any]], PartitionResult]:
    rows = normalize_editable_blocks(blocks)
    target = str(target_block or '').strip()
    output: list[dict[str, Any]] = []
    result: PartitionResult | None = None
    for block in rows:
        if block.name == target:
            result = partition_editable_block_axis(block, axis=axis, coordinate=coordinate, name=split_name)
            output.extend(dict(row) for row in result.child_blocks)
        else:
            output.append(block.to_dict())
    if result is None:
        raise KeyError(f'Editable block not found: {target_block}')
    return editable_blocks_to_rows(normalize_editable_blocks(output)), result


def _find_block(blocks: list[EditableBlock], name: str) -> EditableBlock | None:
    return next((block for block in blocks if block.name == name), None)


def build_partition_plan(blocks: Iterable[dict[str, Any]], split_definitions: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Convert user split definitions into protected surfaces and contact rows.

    The plan is dependency-light and can be shown in the GUI before meshing. Axis
    surface splits are executable now. Oblique plane splits become explicit
    protected surfaces that the future OCC backend can consume without changing
    the GUI contract.
    """
    block_rows = normalize_editable_blocks(blocks)
    split_rows = [dict(row) for row in list(split_definitions or []) if isinstance(row, dict)]
    results: list[PartitionResult] = []
    issues: list[dict[str, Any]] = []
    for index, row in enumerate(split_rows, start=1):
        target = str(row.get('target_block') or row.get('region_name') or row.get('target') or '').strip()
        if not target:
            continue
        block = _find_block(block_rows, target)
        split_name = str(row.get('name') or f'{target}__split_{index:02d}')
        kind = str(row.get('kind') or 'surface').strip().lower() or 'surface'
        if block is None:
            neg_name = str(row.get('negative_name') or row.get('region_a') or '').strip()
            pos_name = str(row.get('positive_name') or row.get('region_b') or '').strip()
            neg = _find_block(block_rows, neg_name) if neg_name else None
            pos = _find_block(block_rows, pos_name) if pos_name else None
            if bool(row.get('partition_applied')) and neg is not None and pos is not None:
                results.append(partition_applied_axis_surface_from_children(neg, pos, axis=str(row.get('axis') or 'z'), coordinate=None if row.get('coordinate') in {None, ''} else float(row.get('coordinate')), parent_name=target, name=split_name))
                continue
            issues.append({'id': f'partition.{split_name}.target_missing', 'severity': 'warning', 'message': f'Split target {target!r} is not present in editable blocks.', 'target': target, 'action': 'Refresh the editable geometry or remove the stale split definition.'})
            continue
        if kind in {'surface', 'axis', 'axis_plane'} and row.get('axis') in {'x', 'y', 'z', None}:
            results.append(partition_editable_block_axis(block, axis=str(row.get('axis') or 'z'), coordinate=None if row.get('coordinate') in {None, ''} else float(row.get('coordinate')), name=split_name))
        elif kind in {'plane', 'oblique_plane'} or row.get('normal') is not None:
            point = row.get('point') or row.get('origin') or block.center
            normal = row.get('normal') or (0.0, 0.0, 1.0)
            results.append(partition_editable_block_by_plane(block, point=point, normal=normal, name=split_name))
        elif kind in {'polyline', 'polyline_extrusion'} or row.get('polyline') is not None:
            results.append(partition_editable_block_by_polyline_extrusion(block, polyline=row.get('polyline') or [], z_min=None if row.get('z_min') in {None, ''} else float(row.get('z_min')), z_max=None if row.get('z_max') in {None, ''} else float(row.get('z_max')), name=split_name))
        else:
            issues.append({'id': f'partition.{split_name}.unsupported_kind', 'severity': 'warning', 'message': f'Split kind {kind!r} is recorded but not executable by the lightweight partition engine.', 'target': target, 'action': 'Use an axis/surface split, oblique plane split, or polyline extrusion split.'})
    protected = [res.split_surface.to_dict() for res in results if res.split_surface is not None]
    contact_rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for res in results:
        contact_rows.extend([dict(row) for row in res.contact_pair_rows])
        selections.extend([dict(row) for row in res.named_selections])
        issues.extend([dict(issue) for issue in res.issues])
    try:
        from geoai_simkit.geometry.occ_partition import build_gmsh_occ_partition_plan
        occ_partition = build_gmsh_occ_partition_plan([block.to_dict() for block in block_rows], split_rows)
    except Exception as exc:  # pragma: no cover - optional adapter path
        occ_partition = {'contract': 'gmsh_occ_partition_plan_v1', 'backend_available': False, 'issues': [{'id': 'occ.plan_failed', 'severity': 'warning', 'message': str(exc), 'target': 'occ_partition', 'action': 'Check OCC split definitions.'}], 'summary': {'backend_available': False, 'issue_count': 1}}
    return {
        'contract': 'geometry_partition_plan_v2',
        'result_count': len(results),
        'executable_axis_split_count': sum(1 for res in results if res.mode == 'axis_exact'),
        'virtual_plane_split_count': sum(1 for res in results if res.mode == 'plane_virtual'),
        'protected_surface_count': len(protected),
        'protected_surfaces': protected,
        'split_definitions': [dict(row) for row in split_rows],
        'contact_pair_rows': contact_rows,
        'named_selections': selections,
        'issues': issues,
        'occ_partition': occ_partition,
        'results': [res.to_dict() for res in results],
    }


__all__ = [
    'PartitionResult',
    'SplitSurface',
    'apply_axis_partition_to_blocks',
    'build_partition_plan',
    'partition_editable_block_axis',
    'partition_editable_block_by_plane',
    'partition_editable_block_by_polyline_extrusion',
    'partition_applied_axis_surface_from_children',
    'plane_aabb_intersection_polygon',
]
