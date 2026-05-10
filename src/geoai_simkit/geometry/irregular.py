from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from geoai_simkit.geometry.topology_kernel import Point3, polygon_area_3d


def _point2(value: Sequence[Any]) -> tuple[float, float]:
    vals = list(value)[:2]
    if len(vals) != 2:
        raise ValueError('2D point must contain x and y.')
    return (float(vals[0]), float(vals[1]))


def _point3(value: Sequence[Any]) -> Point3:
    vals = list(value)[:3]
    if len(vals) != 3:
        raise ValueError('3D point must contain x, y and z.')
    return (float(vals[0]), float(vals[1]), float(vals[2]))


@dataclass(frozen=True, slots=True)
class TerrainSurfaceSpec:
    name: str
    points: tuple[Point3, ...]
    role: str = 'terrain'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name, 'kind': 'terrain_surface', 'role': self.role, 'points': [[float(v) for v in p] for p in self.points], 'point_count': len(self.points), 'metadata': dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class SlopedLayerSpec:
    name: str
    bounds: tuple[float, float, float, float]
    z_at_xmin: float
    z_at_xmax: float
    role: str = 'sloped_layer'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_surface_polygon(self) -> tuple[Point3, ...]:
        xmin, xmax, ymin, ymax = self.bounds
        return ((xmin, ymin, self.z_at_xmin), (xmax, ymin, self.z_at_xmax), (xmax, ymax, self.z_at_xmax), (xmin, ymax, self.z_at_xmin))

    def to_dict(self) -> dict[str, Any]:
        polygon = self.to_surface_polygon()
        return {'name': self.name, 'kind': 'sloped_layer_surface', 'role': self.role, 'bounds': [float(v) for v in self.bounds], 'z_at_xmin': float(self.z_at_xmin), 'z_at_xmax': float(self.z_at_xmax), 'polygon': [[float(v) for v in p] for p in polygon], 'area': float(polygon_area_3d(polygon)), 'metadata': dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class WallAlignmentSpec:
    name: str
    polyline: tuple[tuple[float, float], ...]
    z_min: float
    z_max: float
    thickness: float = 0.8
    role: str = 'wall'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_split_definition(self, target_block: str) -> dict[str, Any]:
        return {'name': f'{self.name}:alignment_split', 'target_block': target_block, 'kind': 'polyline_extrusion', 'polyline': [[x, y, self.z_min] for x, y in self.polyline], 'z_min': float(self.z_min), 'z_max': float(self.z_max), 'source': 'irregular.wall_alignment', 'metadata': {'wall_alignment': self.name, 'thickness': float(self.thickness), **dict(self.metadata)}}

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name, 'kind': 'wall_alignment', 'role': self.role, 'polyline': [[float(x), float(y)] for x, y in self.polyline], 'point_count': len(self.polyline), 'z_min': float(self.z_min), 'z_max': float(self.z_max), 'thickness': float(self.thickness), 'metadata': dict(self.metadata)}


def normalize_irregular_surfaces(parameters: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(parameters or {})
    terrain_rows: list[dict[str, Any]] = []
    for index, row in enumerate(list(params.get('terrain_surfaces', []) or []), start=1):
        if not isinstance(row, dict):
            continue
        pts = tuple(_point3(p) for p in list(row.get('points', []) or []) if len(list(p)) >= 3)
        if pts:
            terrain_rows.append(TerrainSurfaceSpec(str(row.get('name') or f'terrain_{index:02d}'), pts, metadata=dict(row.get('metadata', {}) or {})).to_dict())
    slope_rows: list[dict[str, Any]] = []
    for index, row in enumerate(list(params.get('slope_surfaces', params.get('sloped_layers', [])) or []), start=1):
        if not isinstance(row, dict):
            continue
        bounds = tuple(float(v) for v in list(row.get('bounds', (-10.0, 10.0, -10.0, 10.0)))[:4])
        if len(bounds) != 4:
            continue
        slope_rows.append(SlopedLayerSpec(str(row.get('name') or f'sloped_layer_{index:02d}'), bounds, float(row.get('z_at_xmin', row.get('z_left', 0.0)) or 0.0), float(row.get('z_at_xmax', row.get('z_right', 0.0)) or 0.0), metadata=dict(row.get('metadata', {}) or {})).to_dict())
    wall_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    for index, row in enumerate(list(params.get('wall_alignments', []) or []), start=1):
        if not isinstance(row, dict):
            continue
        poly = tuple(_point2(p) for p in list(row.get('polyline', []) or []) if len(list(p)) >= 2)
        if len(poly) < 2:
            continue
        wall = WallAlignmentSpec(str(row.get('name') or f'wall_alignment_{index:02d}'), poly, float(row.get('z_min', -20.0)), float(row.get('z_max', 0.0)), float(row.get('thickness', 0.8) or 0.8), metadata=dict(row.get('metadata', {}) or {}))
        wall_rows.append(wall.to_dict())
        target = str(row.get('target_block') or params.get('default_wall_target_block') or 'soil_mass')
        split_rows.append(wall.to_split_definition(target))
    return {
        'contract': 'irregular_geotech_geometry_v1',
        'terrain_surfaces': terrain_rows,
        'slope_surfaces': slope_rows,
        'wall_alignments': wall_rows,
        'derived_split_definitions': split_rows,
        'summary': {
            'terrain_surface_count': len(terrain_rows),
            'slope_surface_count': len(slope_rows),
            'wall_alignment_count': len(wall_rows),
            'derived_split_count': len(split_rows),
            'supports_non_rectangular_wall_alignment': True,
            'supports_sloped_ground_and_layer_surfaces': True,
        },
    }


__all__ = ['SlopedLayerSpec', 'TerrainSurfaceSpec', 'WallAlignmentSpec', 'normalize_irregular_surfaces']
