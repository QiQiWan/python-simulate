from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable


def _slug(value: str, *, fallback: str = 'block') -> str:
    text = ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in str(value or '').strip())
    text = '_'.join(part for part in text.split('_') if part)
    return text or fallback


def _float_tuple(values: Iterable[Any], *, length: int, default: float = 0.0) -> tuple[float, ...]:
    out = [float(default)] * length
    for index, value in enumerate(list(values or [])[:length]):
        out[index] = float(value)
    return tuple(out)


def normalize_bounds(bounds: Iterable[Any] | None) -> tuple[float, float, float, float, float, float]:
    raw = _float_tuple(bounds or (-5.0, 5.0, -5.0, 5.0, -5.0, 0.0), length=6)
    xmin, xmax, ymin, ymax, zmin, zmax = raw
    if xmax < xmin:
        xmin, xmax = xmax, xmin
    if ymax < ymin:
        ymin, ymax = ymax, ymin
    if zmax < zmin:
        zmin, zmax = zmax, zmin
    eps = 1.0e-6
    if abs(xmax - xmin) < eps:
        xmax = xmin + eps
    if abs(ymax - ymin) < eps:
        ymax = ymin + eps
    if abs(zmax - zmin) < eps:
        zmax = zmin + eps
    return (float(xmin), float(xmax), float(ymin), float(ymax), float(zmin), float(zmax))


@dataclass(frozen=True, slots=True)
class EditableBlock:
    """Serializable block used by the v5 geometry editor.

    The object deliberately stores a simple axis-aligned solid first. It is not a
    replacement for CAD; it is a reliable modeling primitive that can be selected,
    assigned to materials/stages, split, meshed, and carried through the FE case.
    """

    name: str
    bounds: tuple[float, float, float, float, float, float]
    role: str = 'soil'
    material_name: str | None = None
    mesh_size: float | None = None
    visible: bool = True
    locked: bool = False
    nx: int = 2
    ny: int = 2
    nz: int = 2
    active_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, fallback_index: int = 1) -> 'EditableBlock':
        name = _slug(str(payload.get('name') or payload.get('region_name') or f'block_{fallback_index:02d}'), fallback=f'block_{fallback_index:02d}')
        return cls(
            name=name,
            bounds=normalize_bounds(payload.get('bounds') or payload.get('box_bounds')),
            role=str(payload.get('role') or 'soil'),
            material_name=None if payload.get('material_name') in {None, ''} else str(payload.get('material_name')),
            mesh_size=None if payload.get('mesh_size') in {None, ''} else float(payload.get('mesh_size')),
            visible=bool(payload.get('visible', True)),
            locked=bool(payload.get('locked', False)),
            nx=max(1, int(payload.get('nx', 2) or 2)),
            ny=max(1, int(payload.get('ny', 2) or 2)),
            nz=max(1, int(payload.get('nz', 2) or 2)),
            active_stages=tuple(str(item) for item in list(payload.get('active_stages', ()) or ()) if str(item)),
            metadata=dict(payload.get('metadata', {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'name': self.name,
            'region_name': self.name,
            'bounds': [float(v) for v in self.bounds],
            'role': self.role,
            'visible': bool(self.visible),
            'locked': bool(self.locked),
            'nx': int(self.nx),
            'ny': int(self.ny),
            'nz': int(self.nz),
            'active_stages': list(self.active_stages),
            'metadata': dict(self.metadata),
        }
        if self.material_name:
            payload['material_name'] = self.material_name
        if self.mesh_size is not None:
            payload['mesh_size'] = float(self.mesh_size)
        return payload

    @property
    def center(self) -> tuple[float, float, float]:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return (0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax))

    @property
    def size(self) -> tuple[float, float, float]:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return (xmax - xmin, ymax - ymin, zmax - zmin)

    @property
    def volume(self) -> float:
        sx, sy, sz = self.size
        return float(max(sx, 0.0) * max(sy, 0.0) * max(sz, 0.0))

    def translated(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> 'EditableBlock':
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return replace(self, bounds=(xmin + dx, xmax + dx, ymin + dy, ymax + dy, zmin + dz, zmax + dz))

    def scaled_about_center(self, sx: float = 1.0, sy: float = 1.0, sz: float = 1.0) -> 'EditableBlock':
        cx, cy, cz = self.center
        dx, dy, dz = self.size
        new = (
            cx - 0.5 * dx * float(sx), cx + 0.5 * dx * float(sx),
            cy - 0.5 * dy * float(sy), cy + 0.5 * dy * float(sy),
            cz - 0.5 * dz * float(sz), cz + 0.5 * dz * float(sz),
        )
        return replace(self, bounds=normalize_bounds(new))

    def split(self, *, axis: str = 'z', coordinate: float | None = None, negative_name: str | None = None, positive_name: str | None = None) -> tuple['EditableBlock', 'EditableBlock']:
        axis_key = str(axis or 'z').strip().lower()
        axis_index = {'x': 0, 'y': 1, 'z': 2}.get(axis_key)
        if axis_index is None:
            raise ValueError(f'Unsupported split axis: {axis}')
        bounds = list(self.bounds)
        lo = bounds[2 * axis_index]
        hi = bounds[2 * axis_index + 1]
        cut = 0.5 * (lo + hi) if coordinate is None else float(coordinate)
        eps = max(abs(hi - lo) * 1.0e-6, 1.0e-6)
        cut = min(max(cut, lo + eps), hi - eps)
        neg_bounds = list(bounds)
        pos_bounds = list(bounds)
        neg_bounds[2 * axis_index + 1] = cut
        pos_bounds[2 * axis_index] = cut
        neg_name = _slug(negative_name or f'{self.name}_{axis_key}_neg')
        pos_name = _slug(positive_name or f'{self.name}_{axis_key}_pos')
        neg_meta = {**self.metadata, 'split_parent': self.name, 'split_axis': axis_key, 'split_side': 'negative'}
        pos_meta = {**self.metadata, 'split_parent': self.name, 'split_axis': axis_key, 'split_side': 'positive'}
        return (
            replace(self, name=neg_name, bounds=normalize_bounds(neg_bounds), metadata=neg_meta),
            replace(self, name=pos_name, bounds=normalize_bounds(pos_bounds), metadata=pos_meta),
        )


def normalize_editable_blocks(rows: Iterable[dict[str, Any]] | None) -> list[EditableBlock]:
    blocks: list[EditableBlock] = []
    seen: set[str] = set()
    for index, row in enumerate(list(rows or []), start=1):
        if not isinstance(row, dict):
            continue
        block = EditableBlock.from_dict(row, fallback_index=index)
        base = block.name
        name = base
        suffix = 2
        while name in seen:
            name = f'{base}_{suffix}'
            suffix += 1
        seen.add(name)
        if name != block.name:
            block = replace(block, name=name)
        blocks.append(block)
    return blocks


def editable_blocks_to_rows(blocks: Iterable[EditableBlock]) -> list[dict[str, Any]]:
    return [block.to_dict() for block in blocks]


def default_editable_pit_blocks(parameters: dict[str, Any] | None = None) -> list[EditableBlock]:
    params = dict(parameters or {})
    length = float(params.get('length', 60.0) or 60.0)
    width = float(params.get('width', 30.0) or 30.0)
    depth = float(params.get('depth', 20.0) or 20.0)
    soil_depth = float(params.get('soil_depth', max(depth * 2.0, 40.0)) or max(depth * 2.0, 40.0))
    wall_t = float(params.get('wall_thickness', 0.8) or 0.8)
    half_l = 0.5 * length
    half_w = 0.5 * width
    outer_l = half_l + wall_t
    outer_w = half_w + wall_t
    return [
        EditableBlock('soil_mass', (-outer_l, outer_l, -outer_w, outer_w, -soil_depth, 0.0), role='soil', nx=6, ny=4, nz=6, metadata={'template': 'pit'}),
        EditableBlock('soil_excavation_1', (-half_l, half_l, -half_w, half_w, -0.5 * depth, 0.0), role='excavation', nx=4, ny=3, nz=2, metadata={'template': 'pit', 'stage_hint': 'excavate_1'}),
        EditableBlock('soil_excavation_2', (-half_l, half_l, -half_w, half_w, -depth, -0.5 * depth), role='excavation', nx=4, ny=3, nz=2, metadata={'template': 'pit', 'stage_hint': 'excavate_2'}),
        EditableBlock('wall_north', (-outer_l, outer_l, half_w, outer_w, -depth, 0.0), role='wall', nx=6, ny=1, nz=4, metadata={'template': 'pit'}),
        EditableBlock('wall_south', (-outer_l, outer_l, -outer_w, -half_w, -depth, 0.0), role='wall', nx=6, ny=1, nz=4, metadata={'template': 'pit'}),
        EditableBlock('wall_east', (half_l, outer_l, -half_w, half_w, -depth, 0.0), role='wall', nx=1, ny=4, nz=4, metadata={'template': 'pit'}),
        EditableBlock('wall_west', (-outer_l, -half_l, -half_w, half_w, -depth, 0.0), role='wall', nx=1, ny=4, nz=4, metadata={'template': 'pit'}),
    ]


def build_editable_geometry_payload(parameters: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(parameters or {})
    blocks = normalize_editable_blocks(params.get('blocks') or params.get('editable_blocks') or [])
    rows: list[dict[str, Any]] = []
    total_volume = 0.0
    for block in blocks:
        row = block.to_dict()
        cx, cy, cz = block.center
        sx, sy, sz = block.size
        row.update({
            'center': [cx, cy, cz],
            'size': [sx, sy, sz],
            'volume': block.volume,
            'mesh_cell_hint': int(max(1, block.nx) * max(1, block.ny) * max(1, block.nz)),
        })
        total_volume += block.volume
        rows.append(row)
    topology_payload: dict[str, Any] = {}
    topology_contact_summary: dict[str, Any] = {}
    partition_plan: dict[str, Any] = {}
    irregular_payload: dict[str, Any] = {}
    pit_modeling_payload: dict[str, Any] = {}
    stratigraphy_payload: dict[str, Any] = {}
    dirty_state_payload: dict[str, Any] = {}
    try:
        from geoai_simkit.geometry.topology_kernel import build_topology_payload_from_blocks
        from geoai_simkit.geometry.block_contact import detect_topology_face_contacts, summarize_block_contacts
        from geoai_simkit.geometry.partition_engine import build_partition_plan
        from geoai_simkit.geometry.irregular import normalize_irregular_surfaces
        from geoai_simkit.geometry.dirty_state import summarize_dirty_state
        from geoai_simkit.geometry.pit_modeling import PitModelingToolkit
        from geoai_simkit.geometry.stratigraphy import StratigraphyModeler

        irregular_payload = normalize_irregular_surfaces(params)
        pit_modeling_payload = PitModelingToolkit().build_plan(dict(params.get("pit_modeling", {}) or params))
        stratigraphy_payload = StratigraphyModeler().build_surfaces_from_boreholes(list(params.get("boreholes", []) or []))
        dirty_state_payload = summarize_dirty_state(params)
        topology_payload = build_topology_payload_from_blocks(rows)
        topology_contacts = detect_topology_face_contacts(topology_payload)
        topology_contact_summary = summarize_block_contacts(topology_contacts)
        split_definitions = list(params.get('block_splits') or []) + list(irregular_payload.get('derived_split_definitions', []) or [])
        partition_plan = build_partition_plan(rows, split_definitions)
    except Exception as exc:  # pragma: no cover - defensive GUI payload path
        topology_payload = {
            'summary': {'kernel': 'editable_block_topology_v1', 'issue_count': 1},
            'issues': [{
                'id': 'topology.payload_failed',
                'severity': 'warning',
                'message': str(exc),
                'target': 'geometry_studio',
                'action': 'Check editable block bounds and split definitions.',
            }],
        }

    topology_summary = dict(topology_payload.get('summary', {}) or {})
    partition_summary = {
        'result_count': int(partition_plan.get('result_count', 0) or 0),
        'protected_surface_count': int(partition_plan.get('protected_surface_count', 0) or 0),
        'executable_axis_split_count': int(partition_plan.get('executable_axis_split_count', 0) or 0),
        'virtual_plane_split_count': int(partition_plan.get('virtual_plane_split_count', 0) or 0),
        'polyline_extrusion_split_count': sum(1 for row in list(partition_plan.get('results', []) or []) if str(row.get('mode') or '') == 'polyline_virtual'),
        'occ_backend_available': bool(dict(partition_plan.get('occ_partition', {}) or {}).get('backend_available', False)),
    }
    return {
        'source_kind': 'editable_blocks',
        'block_rows': rows,
        'block_count': len(rows),
        'total_volume': total_volume,
        'supports_block_create': True,
        'supports_block_delete': True,
        'supports_block_duplicate': True,
        'supports_axis_split': True,
        'supports_plane_split_preview': True,
        'supports_named_selections': True,
        'supports_face_selection': True,
        'supports_protected_split_faces': True,
        'supports_occ_solid_partition': True,
        'supports_polyline_extrusion_split': True,
        'supports_irregular_wall_alignment': True,
        'supports_sloped_surfaces': True,
        'supports_brep_document': True,
        'supports_solver_face_sets': True,
        'supports_mesh_size_fields': True,
        'supports_mesh_quality_report': True,
        'supports_undo': True,
        'selected_block_name': str(params.get('selected_block_name') or (rows[0]['name'] if rows else '')),
        'topology_document': topology_payload,
        'topology_summary': topology_summary,
        'named_selection_rows': [*list(topology_payload.get('named_selections', []) or []), *[dict(row) for row in list(params.get('named_selections', []) or []) if isinstance(row, dict)]],
        'face_rows': list(topology_payload.get('faces', []) or []),
        'solid_rows': list(topology_payload.get('solids', []) or []),
        'topology_contact_summary': topology_contact_summary,
        'partition_plan': partition_plan,
        'block_splits': list(params.get('block_splits') or []),
        'selected_topology_entity': dict(params.get('selected_topology_entity') or {}),
        'selected_face_name': str(params.get('selected_face_name') or ''),
        'mesh_size_controls': [dict(row) for row in list(params.get('mesh_size_controls', []) or []) if isinstance(row, dict)],
        'topology_entity_bindings': dict(params.get('topology_entity_bindings', {}) or {}),
        'brep_document': dict(params.get('brep_document', {}) or {}),
        'solver_face_set_rows': [dict(row) for row in list(params.get('solver_face_set_rows', []) or []) if isinstance(row, dict)],
        'mesh_quality_report': dict(params.get('mesh_quality_report', {}) or {}),
        'geometry_dirty_state': dirty_state_payload or dict(params.get('geometry_dirty_state', {}) or {}),
        'binding_transfer_report': dict(params.get('binding_transfer_report', {}) or {}),
        'pit_modeling_plan': pit_modeling_payload or dict(params.get('pit_modeling', {}) or {}),
        'stratigraphy_surface_plan': stratigraphy_payload,
        'partition_summary': partition_summary,
        'protected_surface_rows': list(partition_plan.get('protected_surfaces', []) or []),
        'occ_partition': dict(partition_plan.get('occ_partition', {}) or {}),
        'irregular_geometry': irregular_payload,
        'irregular_geometry_summary': dict(irregular_payload.get('summary', {}) or {}),
        'wall_alignment_rows': list(irregular_payload.get('wall_alignments', []) or []),
        'slope_surface_rows': list(irregular_payload.get('slope_surfaces', []) or []),
        'terrain_surface_rows': list(irregular_payload.get('terrain_surfaces', []) or []),
    }


def build_editable_blocks_scene(parameters: dict[str, Any] | None):
    """Build a PyVista MultiBlock from editable block definitions.

    PyVista is imported lazily so the editor payload remains usable in headless
    environments. The actual model build still requires the geometry dependency.
    """
    try:
        import numpy as np
        import pyvista as pv
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional deps
        raise ModuleNotFoundError('editable_blocks geometry requires numpy and pyvista to build the mesh scene.') from exc

    params = dict(parameters or {})
    blocks = normalize_editable_blocks(params.get('blocks') or params.get('editable_blocks') or [])
    if not blocks:
        blocks = default_editable_pit_blocks(params)
    multiblock = pv.MultiBlock()
    for block in blocks:
        xmin, xmax, ymin, ymax, zmin, zmax = block.bounds
        x = np.linspace(xmin, xmax, max(1, int(block.nx)) + 1)
        y = np.linspace(ymin, ymax, max(1, int(block.ny)) + 1)
        z = np.linspace(zmin, zmax, max(1, int(block.nz)) + 1)
        grid = pv.RectilinearGrid(x, y, z).cast_to_unstructured_grid()
        grid.cell_data['region_name'] = np.array([block.name] * grid.n_cells)
        grid.field_data['region_name'] = np.array([block.name])
        grid.field_data['role'] = np.array([block.role])
        grid.field_data['topology_entity_id'] = np.array([f'solid:{block.name}'])
        grid.field_data['topology_kind'] = np.array(['solid'])
        multiblock[block.name] = grid
    return multiblock


__all__ = [
    'EditableBlock',
    'build_editable_blocks_scene',
    'build_editable_geometry_payload',
    'default_editable_pit_blocks',
    'editable_blocks_to_rows',
    'normalize_bounds',
    'normalize_editable_blocks',
]
