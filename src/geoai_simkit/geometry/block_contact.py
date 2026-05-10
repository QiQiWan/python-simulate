from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class AxisAlignedBlock:
    """Dependency-light block box used for contact/interface preflight checks."""

    name: str
    bounds: tuple[float, float, float, float, float, float]
    role: str = 'soil'
    material_name: str | None = None
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: dict[str, Any], *, fallback_name: str = 'block') -> 'AxisAlignedBlock':
        raw_bounds = row.get('bounds') or row.get('box_bounds') or row.get('extent') or ()
        values = tuple(float(v) for v in list(raw_bounds)[:6])
        if len(values) != 6:
            raise ValueError(f'Block {row.get("name", fallback_name)!r} does not define 6 bounds values.')
        xmin, xmax, ymin, ymax, zmin, zmax = values
        bounds = (min(xmin, xmax), max(xmin, xmax), min(ymin, ymax), max(ymin, ymax), min(zmin, zmax), max(zmin, zmax))
        return cls(
            name=str(row.get('name') or row.get('region_name') or fallback_name),
            bounds=bounds,
            role=str(row.get('role') or 'soil'),
            material_name=None if row.get('material_name') in {None, ''} else str(row.get('material_name')),
            active_stages=tuple(str(v) for v in list(row.get('active_stages', ()) or ()) if str(v)),
            metadata=dict(row.get('metadata', {}) or {}),
        )

    @property
    def volume(self) -> float:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return max(0.0, xmax - xmin) * max(0.0, ymax - ymin) * max(0.0, zmax - zmin)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'bounds': [float(v) for v in self.bounds],
            'role': self.role,
            'material_name': self.material_name,
            'active_stages': list(self.active_stages),
            'volume': float(self.volume),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BlockContactPair:
    """One detected face contact between two axis-aligned blocks."""

    name: str
    block_a: str
    block_b: str
    region_a: str = ''
    region_b: str = ''
    axis: str = ''
    coordinate: float = 0.0
    overlap_area: float = 0.0
    role_a: str = 'soil'
    role_b: str = 'soil'
    contact_mode: str = 'shared_face'
    mesh_policy: str = 'merge_or_tie'
    confidence: str = 'axis_aligned_exact'
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'block_a': self.block_a,
            'block_b': self.block_b,
            'region_a': self.region_a or self.block_a,
            'region_b': self.region_b or self.block_b,
            'axis': self.axis,
            'coordinate': float(self.coordinate),
            'overlap_area': float(self.overlap_area),
            'role_a': self.role_a,
            'role_b': self.role_b,
            'contact_mode': self.contact_mode,
            'mesh_policy': self.mesh_policy,
            'confidence': self.confidence,
            'active_stages': list(self.active_stages),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ContactInterfaceAsset:
    """Aggregated contact/interface asset derived from detected block contacts."""

    interface_name: str
    region_a: str
    region_b: str
    contact_mode: str
    mesh_policy: str
    request_type: str
    solver_policy: str
    pair_count: int
    total_overlap_area: float
    source_blocks: tuple[str, ...] = ()
    active_stages: tuple[str, ...] = ()
    can_materialize: bool = True
    needs_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'interface_name': self.interface_name,
            'region_a': self.region_a,
            'region_b': self.region_b,
            'contact_mode': self.contact_mode,
            'mesh_policy': self.mesh_policy,
            'request_type': self.request_type,
            'solver_policy': self.solver_policy,
            'pair_count': int(self.pair_count),
            'total_overlap_area': float(self.total_overlap_area),
            'source_blocks': list(self.source_blocks),
            'active_stages': list(self.active_stages),
            'can_materialize': bool(self.can_materialize),
            'needs_review': bool(self.needs_review),
            'metadata': dict(self.metadata),
        }



def _overlap_length(a0: float, a1: float, b0: float, b1: float, tol: float) -> float:
    lo = max(float(a0), float(b0))
    hi = min(float(a1), float(b1))
    length = hi - lo
    return float(length) if length > tol else 0.0


def _touches(a_hi: float, b_lo: float, tol: float) -> bool:
    scale = max(1.0, abs(float(a_hi)), abs(float(b_lo)))
    return abs(float(a_hi) - float(b_lo)) <= max(float(tol), scale * float(tol))


def _pair_contact_policy(role_a: str, role_b: str) -> tuple[str, str]:
    roles = {str(role_a).lower(), str(role_b).lower()}
    if 'wall' in roles or 'support' in roles or 'structure' in roles:
        return 'wall_soil_interface', 'duplicate_contact_nodes'
    if 'excavation' in roles:
        return 'excavation_release_face', 'keep_split_boundary'
    return 'soil_continuity', 'merge_or_tie'


def _shared_stage_names(a: AxisAlignedBlock, b: AxisAlignedBlock) -> tuple[str, ...]:
    if not a.active_stages and not b.active_stages:
        return ()
    if not a.active_stages:
        return tuple(b.active_stages)
    if not b.active_stages:
        return tuple(a.active_stages)
    return tuple(name for name in a.active_stages if name in set(b.active_stages))


def detect_axis_aligned_block_contacts(
    blocks: Iterable[AxisAlignedBlock | dict[str, Any]],
    *,
    tolerance: float = 1.0e-7,
    min_overlap_area: float = 1.0e-10,
) -> list[BlockContactPair]:
    """Detect exact face contacts for axis-aligned block boxes.

    The function is intentionally dependency-light so it can run in GUI preflight,
    command-line demos and tests before PyVista/Gmsh are available. It is not a
    Boolean geometry kernel; it only detects clean, face-to-face box contacts.
    """
    block_list: list[AxisAlignedBlock] = []
    for index, item in enumerate(list(blocks or []), start=1):
        if isinstance(item, AxisAlignedBlock):
            block_list.append(item)
        elif isinstance(item, dict):
            block_list.append(AxisAlignedBlock.from_mapping(item, fallback_name=f'block_{index:03d}'))
    pairs: list[BlockContactPair] = []
    axes = (
        ('x', 0, 1, (2, 3), (4, 5)),
        ('y', 2, 3, (0, 1), (4, 5)),
        ('z', 4, 5, (0, 1), (2, 3)),
    )
    for i, a in enumerate(block_list):
        for b in block_list[i + 1:]:
            ab = a.bounds
            bb = b.bounds
            for axis_name, a_min_idx, a_max_idx, span_1, span_2 in axes:
                coordinate: float | None = None
                if _touches(ab[a_max_idx], bb[a_min_idx], tolerance):
                    coordinate = 0.5 * (ab[a_max_idx] + bb[a_min_idx])
                elif _touches(bb[a_max_idx], ab[a_min_idx], tolerance):
                    coordinate = 0.5 * (bb[a_max_idx] + ab[a_min_idx])
                if coordinate is None:
                    continue
                ov1 = _overlap_length(ab[span_1[0]], ab[span_1[1]], bb[span_1[0]], bb[span_1[1]], tolerance)
                ov2 = _overlap_length(ab[span_2[0]], ab[span_2[1]], bb[span_2[0]], bb[span_2[1]], tolerance)
                area = ov1 * ov2
                if area <= min_overlap_area:
                    continue
                contact_mode, mesh_policy = _pair_contact_policy(a.role, b.role)
                region_a = str(a.metadata.get('region_name') or a.metadata.get('region') or a.name)
                region_b = str(b.metadata.get('region_name') or b.metadata.get('region') or b.name)
                pair_name = f'contact:{a.name}--{b.name}'
                pairs.append(
                    BlockContactPair(
                        name=pair_name,
                        block_a=a.name,
                        block_b=b.name,
                        region_a=region_a,
                        region_b=region_b,
                        axis=axis_name,
                        coordinate=float(coordinate),
                        overlap_area=float(area),
                        role_a=a.role,
                        role_b=b.role,
                        contact_mode=contact_mode,
                        mesh_policy=mesh_policy,
                        active_stages=_shared_stage_names(a, b),
                        metadata={
                            'volume_a': float(a.volume),
                            'volume_b': float(b.volume),
                            'region_a': region_a,
                            'region_b': region_b,
                            'block_a_bounds': list(a.bounds),
                            'block_b_bounds': list(b.bounds),
                        },
                    )
                )
    pairs.sort(key=lambda row: (row.block_a, row.block_b, row.axis, -row.overlap_area))
    return pairs


def _asset_type_for_policy(mesh_policy: str, contact_mode: str) -> tuple[str, str, bool, bool]:
    policy = str(mesh_policy or '').lower()
    mode = str(contact_mode or '').lower()
    if policy == 'duplicate_contact_nodes' or 'wall_soil' in mode:
        return 'node_pair_contact', 'contact', True, False
    if policy == 'keep_split_boundary' or 'excavation' in mode:
        return 'release_boundary', 'separated', True, False
    if policy == 'merge_or_tie':
        return 'continuity_tie', 'tie', False, False
    return 'manual_review', policy or 'unknown', False, True


def build_contact_interface_assets(
    pairs: Iterable[BlockContactPair],
    *,
    aggregate_by_region: bool = True,
) -> tuple[ContactInterfaceAsset, ...]:
    """Aggregate detected block pairs into solver/post-processing contact assets.

    The result is serializable and intentionally independent from PyVista/Gmsh. It
    gives the runtime and GUI a stable handoff object before actual interface
    elements are materialized from a mesh.
    """
    groups: dict[tuple[str, str, str, str], list[BlockContactPair]] = {}
    for pair in list(pairs or []):
        region_a = str(pair.region_a or pair.metadata.get('region_a') or pair.block_a)
        region_b = str(pair.region_b or pair.metadata.get('region_b') or pair.block_b)
        contact_mode = str(pair.contact_mode)
        mesh_policy = str(pair.mesh_policy)
        if region_a == region_b:
            # Contacts between two block records that already belong to the same
            # solver region should not create wall-soil contact constraints. They
            # are internal continuity seams and can stay merged/tied.
            contact_mode = 'same_region_continuity'
            mesh_policy = 'merge_or_tie'
        if aggregate_by_region:
            key_regions = tuple(sorted((region_a, region_b)))
        else:
            key_regions = (pair.block_a, pair.block_b)
        key = (key_regions[0], key_regions[1], contact_mode, mesh_policy)
        groups.setdefault(key, []).append(pair)
    assets: list[ContactInterfaceAsset] = []
    for (region_a, region_b, contact_mode, mesh_policy), rows in groups.items():
        request_type, solver_policy, can_materialize, needs_review = _asset_type_for_policy(mesh_policy, contact_mode)
        stages: list[str] = []
        for row in rows:
            for stage_name in row.active_stages:
                if stage_name and stage_name not in stages:
                    stages.append(stage_name)
        source_blocks = []
        axes: dict[str, int] = {}
        for row in rows:
            source_blocks.extend([row.block_a, row.block_b])
            axes[row.axis] = axes.get(row.axis, 0) + 1
        source_tuple = tuple(dict.fromkeys(source_blocks))
        area = float(sum(float(row.overlap_area) for row in rows))
        assets.append(ContactInterfaceAsset(
            interface_name=f'iface:{region_a}--{region_b}:{request_type}',
            region_a=region_a,
            region_b=region_b,
            contact_mode=contact_mode,
            mesh_policy=mesh_policy,
            request_type=request_type,
            solver_policy=solver_policy,
            pair_count=len(rows),
            total_overlap_area=area,
            source_blocks=source_tuple,
            active_stages=tuple(stages),
            can_materialize=can_materialize,
            needs_review=needs_review,
            metadata={'axes': dict(sorted(axes.items())), 'aggregate_by_region': bool(aggregate_by_region)},
        ))
    assets.sort(key=lambda item: (-item.total_overlap_area, item.region_a, item.region_b, item.request_type))
    return tuple(assets)


def contact_interface_asset_summary(assets: Iterable[ContactInterfaceAsset]) -> dict[str, Any]:
    rows = list(assets or [])
    by_type: dict[str, int] = {}
    by_solver_policy: dict[str, int] = {}
    for item in rows:
        by_type[item.request_type] = by_type.get(item.request_type, 0) + 1
        by_solver_policy[item.solver_policy] = by_solver_policy.get(item.solver_policy, 0) + 1
    return {
        'asset_count': len(rows),
        'materializable_count': sum(1 for item in rows if item.can_materialize),
        'review_count': sum(1 for item in rows if item.needs_review),
        'by_request_type': by_type,
        'by_solver_policy': by_solver_policy,
        'total_overlap_area': float(sum(float(item.total_overlap_area) for item in rows)),
        'assets': [item.to_dict() for item in rows],
    }


def contact_assets_to_policy_rows(assets: Iterable[ContactInterfaceAsset]) -> list[dict[str, Any]]:
    """Convert contact assets into the pipeline interface-request row schema."""
    rows: list[dict[str, Any]] = []
    for item in list(assets or []):
        if item.request_type == 'continuity_tie':
            policy = 'merge_or_tie'
        elif item.request_type == 'release_boundary':
            policy = 'keep_split_boundary'
        elif item.request_type == 'node_pair_contact':
            policy = 'duplicate_contact_nodes'
        else:
            policy = item.mesh_policy
        rows.append({
            'name': item.interface_name,
            'edge_name': item.interface_name,
            'pair_name': item.interface_name,
            'region_a': item.region_a,
            'region_b': item.region_b,
            'slave_region': item.region_a,
            'master_region': item.region_b,
            'mesh_policy': policy,
            'contact_mode': item.contact_mode,
            'active_stages': list(item.active_stages),
            'needs_review': bool(item.needs_review),
            'can_materialize': bool(item.can_materialize),
            'source': 'geometry.block_contact',
            'pair_count': int(item.pair_count),
            'total_overlap_area': float(item.total_overlap_area),
            'source_blocks': list(item.source_blocks),
        })
    return rows




# ---------------------------------------------------------------------------
# v0.8.7 topology-face contact detection
# ---------------------------------------------------------------------------

def _project_face_bbox(points: list[tuple[float, float, float]], normal: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Project a 3D face to its dominant 2D plane and return a bbox.

    This is exact for editable-block box faces and conservative for future planar
    BRep polygons. It keeps contact preflight independent from Shapely/OCC.
    """
    ax = max(range(3), key=lambda i: abs(float(normal[i])))
    if ax == 0:
        coords = [(p[1], p[2]) for p in points]
    elif ax == 1:
        coords = [(p[0], p[2]) for p in points]
    else:
        coords = [(p[0], p[1]) for p in points]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return (min(xs), max(xs), min(ys), max(ys))


def _bbox_overlap_area_2d(a: tuple[float, float, float, float], b: tuple[float, float, float, float], tol: float) -> float:
    ox = min(a[1], b[1]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[2], b[2])
    if ox <= tol or oy <= tol:
        return 0.0
    return float(ox * oy)


def _face_vertex_points(face: dict[str, Any], vertex_lookup: dict[str, tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    for vid in list(face.get('vertex_ids') or []):
        if str(vid) in vertex_lookup:
            pts.append(vertex_lookup[str(vid)])
    return pts


def detect_topology_face_contacts(
    topology_payload: dict[str, Any],
    *,
    tolerance: float = 1.0e-7,
    min_overlap_area: float = 1.0e-10,
) -> list[BlockContactPair]:
    """Detect face-face contacts from an explicit topology document.

    Unlike the old AABB-only detector, this function consumes face entities. It
    is the stable handoff point for future BRep/OCC faces while remaining exact
    for the current editable block model.
    """
    vertices = {
        str(row.get('id')): tuple(float(v) for v in list(row.get('xyz') or [])[:3])
        for row in list(topology_payload.get('vertices') or [])
        if isinstance(row, dict) and row.get('id') and len(list(row.get('xyz') or [])) >= 3
    }
    solids = {str(row.get('id')): dict(row) for row in list(topology_payload.get('solids') or []) if isinstance(row, dict) and row.get('id')}
    faces = [dict(row) for row in list(topology_payload.get('faces') or []) if isinstance(row, dict) and row.get('id')]
    pairs: list[BlockContactPair] = []
    for i, fa in enumerate(faces):
        solid_a = str(fa.get('solid_id') or '')
        if not solid_a:
            continue
        na = tuple(float(v) for v in list(fa.get('normal') or (0.0, 0.0, 1.0))[:3])
        ca = tuple(float(v) for v in list(fa.get('centroid') or (0.0, 0.0, 0.0))[:3])
        pts_a = _face_vertex_points(fa, vertices)
        if len(pts_a) < 3:
            continue
        for fb in faces[i + 1:]:
            solid_b = str(fb.get('solid_id') or '')
            if not solid_b or solid_b == solid_a:
                continue
            nb = tuple(float(v) for v in list(fb.get('normal') or (0.0, 0.0, 1.0))[:3])
            if na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2] > -1.0 + max(1.0e-5, tolerance * 10.0):
                continue
            cb = tuple(float(v) for v in list(fb.get('centroid') or (0.0, 0.0, 0.0))[:3])
            plane_gap = abs((cb[0] - ca[0]) * na[0] + (cb[1] - ca[1]) * na[1] + (cb[2] - ca[2]) * na[2])
            scale = max(1.0, abs(ca[0]), abs(ca[1]), abs(ca[2]), abs(cb[0]), abs(cb[1]), abs(cb[2]))
            if plane_gap > max(tolerance, scale * tolerance):
                continue
            pts_b = _face_vertex_points(fb, vertices)
            if len(pts_b) < 3:
                continue
            area = _bbox_overlap_area_2d(_project_face_bbox(pts_a, na), _project_face_bbox(pts_b, na), tolerance)
            if area <= min_overlap_area:
                continue
            sa = solids.get(solid_a, {})
            sb = solids.get(solid_b, {})
            block_a = str(sa.get('name') or solid_a.replace('solid:', ''))
            block_b = str(sb.get('name') or solid_b.replace('solid:', ''))
            role_a = str(sa.get('role') or fa.get('role') or 'soil')
            role_b = str(sb.get('role') or fb.get('role') or 'soil')
            contact_mode, mesh_policy = _pair_contact_policy(role_a, role_b)
            axis = str(fa.get('label') or '')[:1]
            coordinate = float(ca[{'x': 0, 'y': 1, 'z': 2}.get(axis, 2)]) if axis in {'x', 'y', 'z'} else 0.0
            pairs.append(BlockContactPair(
                name=f"contact:{block_a}--{block_b}:{fa.get('label', 'face')}--{fb.get('label', 'face')}",
                block_a=block_a,
                block_b=block_b,
                region_a=str(sa.get('source_block') or block_a),
                region_b=str(sb.get('source_block') or block_b),
                axis=axis,
                coordinate=coordinate,
                overlap_area=float(area),
                role_a=role_a,
                role_b=role_b,
                contact_mode=contact_mode,
                mesh_policy=mesh_policy,
                confidence='topology_face_overlap',
                metadata={
                    'face_a': str(fa.get('id') or ''),
                    'face_b': str(fb.get('id') or ''),
                    'normal_a': list(na),
                    'normal_b': list(nb),
                    'plane_gap': float(plane_gap),
                },
            ))
    pairs.sort(key=lambda row: (row.block_a, row.block_b, row.axis, -row.overlap_area, row.name))
    return pairs

def summarize_block_contacts(pairs: Iterable[BlockContactPair]) -> dict[str, Any]:
    rows = list(pairs or [])
    by_mode: dict[str, int] = {}
    by_policy: dict[str, int] = {}
    total_area = 0.0
    for pair in rows:
        by_mode[pair.contact_mode] = by_mode.get(pair.contact_mode, 0) + 1
        by_policy[pair.mesh_policy] = by_policy.get(pair.mesh_policy, 0) + 1
        total_area += float(pair.overlap_area)
    assets = build_contact_interface_assets(rows)
    asset_summary = contact_interface_asset_summary(assets)
    return {
        'pair_count': len(rows),
        'total_overlap_area': float(total_area),
        'by_contact_mode': by_mode,
        'by_mesh_policy': by_policy,
        'pairs': [pair.to_dict() for pair in rows],
        'interface_asset_summary': {key: value for key, value in asset_summary.items() if key != 'assets'},
        'interface_assets': asset_summary['assets'],
        'policy_rows': contact_assets_to_policy_rows(assets),
    }


__all__ = [
    'AxisAlignedBlock',
    'BlockContactPair',
    'ContactInterfaceAsset',
    'build_contact_interface_assets',
    'contact_interface_asset_summary',
    'contact_assets_to_policy_rows',
    'detect_axis_aligned_block_contacts',
    'detect_topology_face_contacts',
    'summarize_block_contacts',
]
