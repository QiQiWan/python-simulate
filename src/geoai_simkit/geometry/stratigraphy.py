from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
import math


def _point(row: dict[str, Any]) -> tuple[float, float, dict[str, float]]:
    x = float(row.get('x', row.get('X', 0.0)) or 0.0)
    y = float(row.get('y', row.get('Y', 0.0)) or 0.0)
    layers = row.get('layers') or {}
    if not isinstance(layers, dict):
        layers = {}
    return x, y, {str(k): float(v) for k, v in layers.items()}


def _idw_value(samples: list[tuple[float, float, float]], x: float, y: float, power: float = 2.0) -> float:
    if not samples:
        return 0.0
    weights: list[float] = []
    values: list[float] = []
    for sx, sy, sz in samples:
        d = math.hypot(float(x) - float(sx), float(y) - float(sy))
        if d <= 1.0e-12:
            return float(sz)
        weights.append(1.0 / max(d, 1.0e-12) ** float(power))
        values.append(float(sz))
    total = sum(weights) or 1.0
    return float(sum(w * v for w, v in zip(weights, values)) / total)


def _grid_triangles(resolution: int) -> tuple[tuple[int, int, int], ...]:
    n = max(2, int(resolution or 2))
    tris: list[tuple[int, int, int]] = []
    for ix in range(n - 1):
        for iy in range(n - 1):
            a = ix * n + iy
            b = (ix + 1) * n + iy
            c = (ix + 1) * n + (iy + 1)
            d = ix * n + (iy + 1)
            tris.append((a, b, c))
            tris.append((a, c, d))
    return tuple(tris)


@dataclass(slots=True)
class StratigraphySurface:
    name: str
    samples: tuple[tuple[float, float, float], ...]
    z_mean: float = 0.0
    z_min: float = 0.0
    z_max: float = 0.0
    interpolated_grid: tuple[tuple[float, float, float], ...] = ()
    triangles: tuple[tuple[int, int, int], ...] = ()
    method: str = 'idw'

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'samples': [[float(x), float(y), float(z)] for x, y, z in self.samples],
            'z_mean': float(self.z_mean),
            'z_min': float(self.z_min),
            'z_max': float(self.z_max),
            'interpolation': self.method,
            'interpolated_grid': [[float(x), float(y), float(z)] for x, y, z in self.interpolated_grid],
            'triangles': [[int(i), int(j), int(k)] for i, j, k in self.triangles],
            'grid_point_count': len(self.interpolated_grid),
            'triangle_count': len(self.triangles),
        }


@dataclass(slots=True)
class StratigraphyLayerSolid:
    name: str
    top_surface: str
    bottom_surface: str
    bounds: tuple[float, float, float, float, float, float]
    material_name: str = ''
    generated_split_surfaces: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'top_surface': self.top_surface,
            'bottom_surface': self.bottom_surface,
            'bounds': [float(v) for v in self.bounds],
            'role': 'soil_layer',
            'material_name': self.material_name,
            'generated_split_surfaces': list(self.generated_split_surfaces),
            'metadata': dict(self.metadata),
        }


class StratigraphyModeler:
    """Build editable stratigraphic surface and layer-solid contracts from boreholes."""

    def _grid_xy(self, points: list[tuple[float, float, dict[str, float]]], resolution: int = 5, padding: float = 0.0) -> list[tuple[float, float]]:
        xs = [p[0] for p in points] or [0.0]
        ys = [p[1] for p in points] or [0.0]
        xmin, xmax = min(xs) - float(padding), max(xs) + float(padding)
        ymin, ymax = min(ys) - float(padding), max(ys) + float(padding)
        n = max(2, int(resolution or 5))
        out: list[tuple[float, float]] = []
        for ix in range(n):
            x = xmin + (xmax - xmin) * ix / max(1, n - 1)
            for iy in range(n):
                y = ymin + (ymax - ymin) * iy / max(1, n - 1)
                out.append((float(x), float(y)))
        return out

    def build_surfaces_from_boreholes(self, boreholes: Iterable[dict[str, Any]], *, grid_resolution: int = 5, padding: float = 0.0, method: str = 'idw') -> dict[str, Any]:
        points = [_point(dict(row)) for row in list(boreholes or []) if isinstance(row, dict)]
        layer_names = sorted({name for _, _, layers in points for name in layers})
        surfaces: list[StratigraphySurface] = []
        issues: list[dict[str, Any]] = []
        n_grid = max(2, int(grid_resolution or 5))
        grid_xy = self._grid_xy(points, resolution=n_grid, padding=padding)
        triangles = _grid_triangles(n_grid)
        for name in layer_names:
            samples = [(x, y, layers[name]) for x, y, layers in points if name in layers]
            if len(samples) < 2:
                issues.append({'id': 'stratigraphy.too_few_samples', 'severity': 'warning', 'layer': name, 'message': 'Layer surface has fewer than two borehole samples.'})
            zs = [p[2] for p in samples] or [0.0]
            interpolated = tuple((gx, gy, _idw_value(samples, gx, gy)) for gx, gy in grid_xy) if samples else ()
            surfaces.append(StratigraphySurface(name=name, samples=tuple(samples), z_mean=sum(zs) / len(zs), z_min=min(zs), z_max=max(zs), interpolated_grid=interpolated, triangles=triangles if interpolated else (), method=method))
        layer_solids = self.build_layer_solids([s.to_dict() for s in surfaces])
        return {
            'contract': 'stratigraphy_surface_plan_v4',
            'surfaces': [surface.to_dict() for surface in surfaces],
            'layer_solids': layer_solids,
            'occ_layer_volume_contract': 'occ_lofted_stratigraphy_layer_volume_v1',
            'occ_layer_volume_enabled': True,
            'generated_blocks': [dict(row) for row in layer_solids],
            'generated_named_selections': [
                {'name': 'stratigraphy_layer_solids', 'kind': 'solid', 'entity_ids': [f'solid:{row["name"]}' for row in layer_solids], 'metadata': {'role': 'soil_layer'}},
                {'name': 'stratigraphy_interfaces', 'kind': 'face', 'entity_ids': [f'protected_surface:{row.get("bottom_surface", "")}' for row in layer_solids if row.get('bottom_surface')], 'metadata': {'role': 'layer_boundary'}},
            ],
            'generated_mesh_controls': [
                {'target': f'protected_surface:{row.get("bottom_surface", "")}', 'source': 'StratigraphyModeler', 'kind': 'distance_threshold', 'size_min': 0.75, 'size_max': 2.5, 'dist_min': 0.0, 'dist_max': 2.0, 'semantic': 'layer_boundary'}
                for row in layer_solids if row.get('bottom_surface')
            ],
            'issues': issues,
            'summary': {'borehole_count': len(points), 'surface_count': len(surfaces), 'layer_solid_count': len(layer_solids), 'issue_count': len(issues), 'interpolation_method': method, 'exports_surface_meshes': True, 'exports_layer_solid_contracts': True, 'exports_occ_loft_fragment_contract': True},
        }

    def build_layer_solids(self, surfaces: Iterable[dict[str, Any]], *, base_z: float | None = None) -> list[dict[str, Any]]:
        rows = [dict(row) for row in list(surfaces or []) if isinstance(row, dict)]
        rows.sort(key=lambda r: float(r.get('z_mean', 0.0) or 0.0), reverse=True)
        if not rows:
            return []
        all_pts: list[tuple[float, float, float]] = []
        for row in rows:
            all_pts.extend([tuple(float(v) for v in p[:3]) for p in list(row.get('interpolated_grid', row.get('samples', [])) or []) if len(p) >= 3])
        xs = [p[0] for p in all_pts] or [0.0]
        ys = [p[1] for p in all_pts] or [0.0]
        zmins = [float(row.get('z_min', 0.0) or 0.0) for row in rows]
        zmaxs = [float(row.get('z_max', 0.0) or 0.0) for row in rows]
        bottom_base = float(base_z if base_z is not None else min(zmins) - max(1.0, abs(max(zmaxs) - min(zmins)) * 0.25))
        solids: list[StratigraphyLayerSolid] = []
        for idx, top in enumerate(rows):
            bottom = rows[idx + 1] if idx + 1 < len(rows) else {'name': 'model_base', 'z_mean': bottom_base, 'z_min': bottom_base, 'z_max': bottom_base}
            top_name = str(top.get('name') or f'surface_{idx:02d}')
            bottom_name = str(bottom.get('name') or f'surface_{idx + 1:02d}')
            z_hi = max(float(top.get('z_max', top.get('z_mean', 0.0)) or 0.0), float(bottom.get('z_max', bottom.get('z_mean', bottom_base)) or bottom_base))
            z_lo = min(float(top.get('z_min', top.get('z_mean', 0.0)) or 0.0), float(bottom.get('z_min', bottom.get('z_mean', bottom_base)) or bottom_base))
            top_grid = [tuple(float(v) for v in p[:3]) for p in list(top.get('interpolated_grid', []) or []) if len(p) >= 3]
            bottom_grid = [tuple(float(v) for v in p[:3]) for p in list(bottom.get('interpolated_grid', []) or []) if len(p) >= 3]
            crossing_count = 0
            if top_grid and bottom_grid and len(top_grid) == len(bottom_grid):
                crossing_count = sum(1 for a, b in zip(top_grid, bottom_grid) if float(a[2]) < float(b[2]))
            crossing_ratio = float(crossing_count) / float(max(1, min(len(top_grid), len(bottom_grid)) or 1))
            solids.append(StratigraphyLayerSolid(
                name=f'soil_layer_{idx + 1:02d}_{top_name}_to_{bottom_name}',
                top_surface=top_name,
                bottom_surface=bottom_name,
                bounds=(min(xs), max(xs), min(ys), max(ys), z_lo, z_hi),
                material_name=f'mat_{top_name}',
                generated_split_surfaces=(top_name, bottom_name),
                metadata={'generated_by': 'StratigraphyModeler', 'top_z_mean': float(top.get('z_mean', 0.0) or 0.0), 'bottom_z_mean': float(bottom.get('z_mean', bottom_base) or bottom_base), 'edit_policy': 'edit_boreholes_or_surfaces_then_remesh', 'occ_layer_solid_contract': 'surface_pair_to_volume_between_layers', 'top_grid_point_count': len(top_grid), 'bottom_grid_point_count': len(bottom_grid), 'surface_crossing_count': int(crossing_count), 'surface_crossing_ratio': float(crossing_ratio)},
            ))
        return [solid.to_dict() for solid in solids]


__all__ = ['StratigraphyModeler', 'StratigraphySurface', 'StratigraphyLayerSolid']
