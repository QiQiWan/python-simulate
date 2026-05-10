from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace
from typing import Any

def _np():
    import numpy as np
    return np

class _SimpleCell:
    def __init__(self, point_ids):
        self.point_ids = tuple(int(i) for i in point_ids)
        self.points = self.point_ids

class SimpleUnstructuredGrid:
    """Small PyVista-like grid used by headless tests and GUI contracts."""
    def __init__(self, points=None, cells=None, celltypes=None, *, region_names=None):
        self.points = _np().asarray(points if points is not None else [], dtype=float).reshape((-1, 3)) if len(points or []) else _np().zeros((0, 3), dtype=float)
        self.cells = list(cells or [])
        self.celltypes = list(celltypes or ['hex8'] * len(self.cells))
        self.point_data: dict[str, Any] = {}
        self.cell_data: dict[str, Any] = {}
        self.field_data: dict[str, Any] = {}
        if region_names is not None:
            self.cell_data['region_name'] = _np().asarray(list(region_names), dtype=object)
    @property
    def n_points(self) -> int:
        return int(len(self.points))
    @property
    def n_cells(self) -> int:
        return int(len(self.cells))
    @property
    def volume(self) -> float:
        if self.n_points == 0 or self.n_cells == 0:
            return 0.0
        mins = self.points.min(axis=0); maxs = self.points.max(axis=0)
        return float(_np().prod(_np().maximum(maxs - mins, 1.0e-9)))
    @property
    def bounds(self) -> tuple[float, float, float, float, float, float]:
        if self.n_points == 0:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        mins = self.points.min(axis=0); maxs = self.points.max(axis=0)
        return (float(mins[0]), float(maxs[0]), float(mins[1]), float(maxs[1]), float(mins[2]), float(maxs[2]))
    def get_cell(self, index: int):
        return _SimpleCell(self.cells[int(index)])
    def cast_to_unstructured_grid(self):
        return self
    def copy(self, deep: bool = True):
        other = SimpleUnstructuredGrid(_np().array(self.points, copy=True), list(self.cells), list(self.celltypes))
        other.point_data = {k: _np().array(v, copy=True) if hasattr(v, '__array__') else v for k, v in self.point_data.items()}
        other.cell_data = {k: _np().array(v, copy=True) if hasattr(v, '__array__') else v for k, v in self.cell_data.items()}
        other.field_data = dict(self.field_data)
        return other

@dataclass(slots=True)
class GeometrySource:
    kind: str = 'parametric_pit'
    parameters: dict[str, Any] = field(default_factory=dict)
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    def resolve(self) -> SimpleUnstructuredGrid:
        p = dict(self.parameters or {})
        kind = str(self.kind).strip().lower()
        if kind in {'stl_geology', 'stl', 'geology_stl', 'stl_surface'}:
            from geoai_simkit.geometry.stl_loader import STLImportOptions
            from geoai_simkit.modules.geology_import import load_geological_stl
            if not self.path:
                raise ValueError('GeometrySource.path is required for STL geological model loading.')
            mesh = load_geological_stl(self.path, STLImportOptions(
                name=str(p.get('name') or p.get('region_name') or ''),
                unit_scale=float(p.get('unit_scale', 1.0) or 1.0),
                merge_tolerance=float(p.get('merge_tolerance', 1.0e-9) or 0.0),
                role=str(p.get('role', 'geology_surface')),
                material_id=str(p.get('material_id', 'imported_geology')),
                flip_normals=bool(p.get('flip_normals', False)),
                center_to_origin=bool(p.get('center_to_origin', False)),
                metadata=dict(self.metadata or {}),
            ))
            return mesh.to_simple_grid(region_name=mesh.name)
        if kind in {'geology_json', 'json_geology', 'geojson'}:
            raise ValueError(
                'GeometrySource.resolve cannot convert structured geological JSON directly to a grid yet. '
                'Use geoai_simkit.modules.geology_import.create_project_from_geology(...) to import it into GeoProjectDocument.'
            )
        if kind in {'foundation_pit_blocks', 'block_foundation_pit', 'pit_blocks'}:
            from geoai_simkit.geometry.foundation_pit_blocks import build_foundation_pit_grid
            return build_foundation_pit_grid(p)
        L = float(p.get('length', 24.0)); W = float(p.get('width', 12.0)); D = float(p.get('depth', 12.0)); SD = float(p.get('soil_depth', max(D * 1.5, D + 4.0)))
        # Four coarse hexahedral blocks: three soil/excavation zones and one wall surrogate.
        x0, x1 = -L / 2, L / 2; y0, y1 = -W / 2, W / 2
        z0, z1, z2, z3 = -SD, -D * 0.65, -D * 0.30, 0.0
        pts = []
        cells = []
        names = []
        def add_hex(xa, xb, ya, yb, za, zb, name):
            base = len(pts)
            pts.extend([(xa,ya,za),(xb,ya,za),(xb,yb,za),(xa,yb,za),(xa,ya,zb),(xb,ya,zb),(xb,yb,zb),(xa,yb,zb)])
            cells.append(tuple(range(base, base + 8))); names.append(name)
        add_hex(x0, x1, y0, y1, z0, z1, 'soil_mass')
        add_hex(x0, x1, y0, y1, z1, z2, 'soil_excavation_2')
        add_hex(x0, x1, y0, y1, z2, z3, 'soil_excavation_1')
        t = float(p.get('wall_thickness', 0.6))
        add_hex(x0 - t, x0, y0, y1, z1, z3, 'wall')
        grid = SimpleUnstructuredGrid(pts, cells, region_names=names)
        grid.field_data['source_kind'] = [self.kind]
        return grid

@dataclass(slots=True)
class RegionSelectorSpec:
    kind: str = 'regions'
    names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MeshAssemblySpec:
    element_family: str = 'auto'
    global_size: float | None = None
    padding: float = 0.0
    local_refinement: dict[str, float] = field(default_factory=dict)
    keep_geometry_copy: bool = False
    only_material_bound_geometry: bool = False
    merge_points: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MaterialAssignmentSpec:
    region_names: tuple[str, ...] = ()
    material_name: str = 'linear_elastic'
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    selector: RegionSelectorSpec | None = None

@dataclass(slots=True)
class BoundaryConditionSpec:
    name: str = 'bc'
    kind: str = 'displacement'
    target: str = 'boundary'
    components: tuple[int, ...] = (0, 1, 2)
    values: tuple[float, ...] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class LoadSpec:
    name: str = 'load'
    kind: str = 'body'
    target: str = 'domain'
    values: tuple[float, ...] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class StageSpec:
    name: str
    predecessor: str | None = None
    activate_regions: tuple[str, ...] = ()
    deactivate_regions: tuple[str, ...] = ()
    boundary_conditions: tuple[Any, ...] = ()
    loads: tuple[Any, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ExcavationStepSpec:
    name: str
    deactivate_regions: tuple[str, ...] = ()
    activate_regions: tuple[str, ...] = ()
    boundary_conditions: tuple[Any, ...] = ()
    loads: tuple[Any, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ContactPairSpec:
    name: str = 'contact'
    master: str = ''
    slave: str = ''
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class StructureGeneratorSpec:
    kind: str = 'demo_pit_supports'
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class InterfaceGeneratorSpec:
    kind: str = 'demo_wall_interfaces'
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MeshPreparationSpec:
    excavation_steps: tuple[ExcavationStepSpec, ...] = ()
    contact_pairs: tuple[ContactPairSpec, ...] = ()
    interface_node_split_mode: str = 'plan'
    interface_duplicate_side: str = 'slave'
    interface_element_mode: str = 'explicit'
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class AnalysisCaseSpec:
    name: str
    geometry: GeometrySource = field(default_factory=GeometrySource)
    mesh: MeshAssemblySpec = field(default_factory=MeshAssemblySpec)
    material_library: tuple[Any, ...] = ()
    materials: tuple[MaterialAssignmentSpec, ...] = ()
    boundary_conditions: tuple[Any, ...] = ()
    loads: tuple[Any, ...] = ()
    stages: tuple[StageSpec, ...] = ()
    structures: tuple[StructureGeneratorSpec, ...] = ()
    interfaces: tuple[InterfaceGeneratorSpec, ...] = ()
    mesh_preparation: MeshPreparationSpec = field(default_factory=MeshPreparationSpec)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class PreparationReport:
    merged_points: bool = True
    merged_point_count: int = 0
    generated_stages: tuple[str, ...] = ()
    generated_interfaces: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class PreparedAnalysisCase:
    model: Any
    report: PreparationReport
