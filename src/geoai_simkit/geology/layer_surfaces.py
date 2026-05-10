from __future__ import annotations

"""Interpolation helpers for borehole-controlled soil layer surfaces."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InterpolatedSurfaceGrid:
    surface_id: str
    points: list[tuple[float, float, float]]
    cells: list[tuple[int, int, int, int]]
    shape: tuple[int, int]
    method: str = "idw"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "points": [list(point) for point in self.points],
            "cells": [list(cell) for cell in self.cells],
            "shape": list(self.shape),
            "method": self.method,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class LayerSurfaceInterpolationResult:
    surface_grids: dict[str, InterpolatedSurfaceGrid]
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.surface_grids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "surface_count": len(self.surface_grids),
            "warnings": list(self.warnings),
            "surface_grids": {key: grid.to_dict() for key, grid in self.surface_grids.items()},
        }


def _surface_bounds(project: Any, padding: float | None) -> tuple[float, float, float, float]:
    contour = getattr(getattr(project, "soil_model", None), "soil_contour", None)
    polygon = list(getattr(contour, "polygon", []) or [])
    if polygon:
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
    else:
        points: list[tuple[float, float, float]] = []
        for surface in getattr(project.soil_model, "soil_layer_surfaces", {}).values():
            points.extend(list(getattr(surface, "control_points", []) or []))
        if not points:
            return (-1.0, 1.0, -1.0, 1.0)
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = max(max(xmax - xmin, ymax - ymin) * 0.05, 1.0) if padding is None else float(padding)
    if xmax <= xmin:
        xmin -= pad
        xmax += pad
    if ymax <= ymin:
        ymin -= pad
        ymax += pad
    return xmin, xmax, ymin, ymax


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [float(start)]
    step = (float(stop) - float(start)) / float(count - 1)
    return [float(start) + step * i for i in range(count)]


def _idw_z(x: float, y: float, control_points: list[tuple[float, float, float]], power: float) -> float:
    numerator = 0.0
    denominator = 0.0
    for px, py, pz in control_points:
        dx = float(x) - float(px)
        dy = float(y) - float(py)
        dist2 = dx * dx + dy * dy
        if dist2 <= 1.0e-18:
            return float(pz)
        weight = 1.0 / (dist2 ** (0.5 * max(float(power), 1.0e-9)))
        numerator += weight * float(pz)
        denominator += weight
    return numerator / denominator if denominator > 0.0 else 0.0


def interpolate_control_points_to_grid(
    surface_id: str,
    control_points: list[tuple[float, float, float]],
    *,
    bounds: tuple[float, float, float, float],
    nx: int = 5,
    ny: int = 5,
    power: float = 2.0,
) -> InterpolatedSurfaceGrid:
    if not control_points:
        raise ValueError(f"Layer surface {surface_id} has no control points to interpolate.")
    nx = max(int(nx), 2)
    ny = max(int(ny), 2)
    xmin, xmax, ymin, ymax = bounds
    xs = _linspace(xmin, xmax, nx)
    ys = _linspace(ymin, ymax, ny)
    points: list[tuple[float, float, float]] = []
    for y in ys:
        for x in xs:
            points.append((float(x), float(y), float(_idw_z(x, y, control_points, power))))
    cells: list[tuple[int, int, int, int]] = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            n0 = j * nx + i
            cells.append((n0, n0 + 1, n0 + 1 + nx, n0 + nx))
    return InterpolatedSurfaceGrid(
        surface_id=surface_id,
        points=points,
        cells=cells,
        shape=(ny, nx),
        method="idw",
        metadata={"control_point_count": len(control_points), "bounds": [xmin, xmax, ymin, ymax], "power": float(power)},
    )


def interpolate_project_layer_surfaces(
    project: Any,
    *,
    nx: int = 5,
    ny: int = 5,
    padding: float | None = None,
    power: float = 2.0,
    update: bool = True,
) -> LayerSurfaceInterpolationResult:
    surfaces = getattr(getattr(project, "soil_model", None), "soil_layer_surfaces", {})
    bounds = _surface_bounds(project, padding)
    grids: dict[str, InterpolatedSurfaceGrid] = {}
    warnings: list[str] = []
    for surface_id, surface in surfaces.items():
        control_points = [tuple(float(v) for v in point) for point in list(getattr(surface, "control_points", []) or [])]
        if not control_points:
            warnings.append(f"Layer surface {surface_id} has no control points and was skipped.")
            continue
        grid = interpolate_control_points_to_grid(
            str(surface_id),
            control_points,
            bounds=bounds,
            nx=nx,
            ny=ny,
            power=power,
        )
        grids[str(surface_id)] = grid
        if update:
            surface.metadata["surface_grid"] = grid.to_dict()
            surface.metadata["interpolation_status"] = "interpolated"
    if update:
        project.metadata.setdefault("layer_surface_interpolation", {}).update(
            {
                "surface_count": len(grids),
                "grid_shape": [max(int(ny), 2), max(int(nx), 2)],
                "method": "idw",
                "warnings": list(warnings),
            }
        )
    return LayerSurfaceInterpolationResult(surface_grids=grids, warnings=warnings)


__all__ = [
    "InterpolatedSurfaceGrid",
    "LayerSurfaceInterpolationResult",
    "interpolate_control_points_to_grid",
    "interpolate_project_layer_surfaces",
]
