from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.pipeline.selectors import resolve_region_selector


@dataclass(slots=True)
class RegionAdjacencyInfo:
    region_a: str
    region_b: str
    shared_point_ids: tuple[int, ...]
    shared_point_count: int
    centroid_distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RegionBoundaryAdjacencyInfo:
    region_a: str
    region_b: str
    shared_face_count: int
    shared_boundary_point_ids: tuple[int, ...]
    shared_point_count: int
    shared_face_area: float
    centroid_distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _BoundaryAccumulator:
    faces: set[tuple[int, ...]] = field(default_factory=set)
    point_ids: set[int] = field(default_factory=set)
    total_face_area: float = 0.0


def _region_point_ids(model: SimulationModel) -> dict[str, np.ndarray]:
    grid = model.to_unstructured_grid()
    out: dict[str, np.ndarray] = {}
    for region in model.region_tags:
        pids: set[int] = set()
        for cid in np.asarray(region.cell_ids, dtype=np.int64):
            try:
                cell = grid.get_cell(int(cid))
            except Exception:
                continue
            for pid in getattr(cell, 'point_ids', []):
                pids.add(int(pid))
        out[str(region.name)] = np.asarray(sorted(pids), dtype=np.int64)
    return out


def _region_cell_ids(model: SimulationModel) -> dict[str, np.ndarray]:
    return {
        str(region.name): np.asarray(region.cell_ids, dtype=np.int64)
        for region in model.region_tags
    }


def _select_regions(model: SimulationModel, selector: Any = None, explicit_names: tuple[str, ...] = ()) -> list[str]:
    names: list[str] = []
    if explicit_names:
        names.extend(str(v) for v in explicit_names if str(v))
    if selector is not None:
        names.extend(resolve_region_selector(model, selector))
    if not names:
        names.extend(str(region.name) for region in model.region_tags)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in names:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _polygon_area_3d(points: np.ndarray) -> float:
    pts = np.asarray(points, dtype=float)
    if pts.shape[0] < 3:
        return 0.0
    origin = pts[0]
    area = 0.0
    for idx in range(1, pts.shape[0] - 1):
        v1 = pts[idx] - origin
        v2 = pts[idx + 1] - origin
        area += 0.5 * float(np.linalg.norm(np.cross(v1, v2)))
    return float(area)


def _cell_faces_from_point_ids(cell_type: int, point_ids: Iterable[int]) -> tuple[tuple[int, ...], ...]:
    ids = tuple(int(v) for v in point_ids)
    if len(ids) < 2:
        return ()
    hexa = int(pv.CellType.HEXAHEDRON)
    voxel = int(pv.CellType.VOXEL)
    tetra = int(pv.CellType.TETRA)
    wedge = int(pv.CellType.WEDGE)
    pyramid = int(pv.CellType.PYRAMID)
    quad = int(pv.CellType.QUAD)
    triangle = int(pv.CellType.TRIANGLE)
    pixel = int(pv.CellType.PIXEL)
    if cell_type == hexa and len(ids) >= 8:
        return (
            (ids[0], ids[1], ids[2], ids[3]),
            (ids[4], ids[5], ids[6], ids[7]),
            (ids[0], ids[1], ids[5], ids[4]),
            (ids[1], ids[2], ids[6], ids[5]),
            (ids[2], ids[3], ids[7], ids[6]),
            (ids[3], ids[0], ids[4], ids[7]),
        )
    if cell_type == voxel and len(ids) >= 8:
        return (
            (ids[0], ids[1], ids[3], ids[2]),
            (ids[4], ids[5], ids[7], ids[6]),
            (ids[0], ids[1], ids[5], ids[4]),
            (ids[2], ids[3], ids[7], ids[6]),
            (ids[0], ids[2], ids[6], ids[4]),
            (ids[1], ids[3], ids[7], ids[5]),
        )
    if cell_type == tetra and len(ids) >= 4:
        return (
            (ids[0], ids[1], ids[2]),
            (ids[0], ids[1], ids[3]),
            (ids[1], ids[2], ids[3]),
            (ids[0], ids[2], ids[3]),
        )
    if cell_type == wedge and len(ids) >= 6:
        return (
            (ids[0], ids[1], ids[2]),
            (ids[3], ids[4], ids[5]),
            (ids[0], ids[1], ids[4], ids[3]),
            (ids[1], ids[2], ids[5], ids[4]),
            (ids[2], ids[0], ids[3], ids[5]),
        )
    if cell_type == pyramid and len(ids) >= 5:
        return (
            (ids[0], ids[1], ids[2], ids[3]),
            (ids[0], ids[1], ids[4]),
            (ids[1], ids[2], ids[4]),
            (ids[2], ids[3], ids[4]),
            (ids[3], ids[0], ids[4]),
        )
    if cell_type in {quad, pixel} and len(ids) >= 4:
        return ((ids[0], ids[1], ids[2], ids[3]),)
    if cell_type == triangle and len(ids) >= 3:
        return ((ids[0], ids[1], ids[2]),)
    if len(ids) >= 3:
        return (ids,)
    return ()


def _compute_region_centroids(points: np.ndarray, region_points: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    centroids: dict[str, np.ndarray] = {}
    for name, ids in region_points.items():
        pts = points[np.asarray(ids, dtype=np.int64)] if ids.size else np.empty((0, 3), dtype=float)
        centroids[name] = np.mean(pts, axis=0) if pts.size else np.zeros(3, dtype=float)
    return centroids


def _selected_region_pairs(
    model: SimulationModel,
    *,
    selector: Any = None,
    region_names: tuple[str, ...] = (),
    left_selector: Any = None,
    left_region_names: tuple[str, ...] = (),
    right_selector: Any = None,
    right_region_names: tuple[str, ...] = (),
) -> tuple[list[str], list[str], bool]:
    if left_selector is not None or left_region_names:
        left = _select_regions(model, left_selector, explicit_names=left_region_names)
        right = _select_regions(model, right_selector, explicit_names=right_region_names)
        pair_mode = True
    else:
        selected = _select_regions(model, selector, explicit_names=region_names)
        left = selected
        right = selected
        pair_mode = False
    return left, right, pair_mode


def compute_region_adjacency(
    model: SimulationModel,
    *,
    selector: Any = None,
    region_names: tuple[str, ...] = (),
    left_selector: Any = None,
    left_region_names: tuple[str, ...] = (),
    right_selector: Any = None,
    right_region_names: tuple[str, ...] = (),
    min_shared_points: int = 1,
) -> tuple[RegionAdjacencyInfo, ...]:
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    region_points = _region_point_ids(model)
    centroids = _compute_region_centroids(points, region_points)
    left, right, pair_mode = _selected_region_pairs(
        model,
        selector=selector,
        region_names=region_names,
        left_selector=left_selector,
        left_region_names=left_region_names,
        right_selector=right_selector,
        right_region_names=right_region_names,
    )
    out: list[RegionAdjacencyInfo] = []
    seen_pairs: set[tuple[str, str]] = set()
    threshold = max(1, int(min_shared_points))
    for region_a in left:
        ids_a = np.asarray(region_points.get(region_a, np.empty((0,), dtype=np.int64)), dtype=np.int64)
        if ids_a.size == 0:
            continue
        centroid_a = centroids.get(region_a, np.zeros(3, dtype=float))
        right_iter = right if pair_mode else [item for item in right if item != region_a]
        for region_b in right_iter:
            if region_a == region_b:
                continue
            key = (region_a, region_b) if pair_mode else tuple(sorted((region_a, region_b)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            ids_b = np.asarray(region_points.get(region_b, np.empty((0,), dtype=np.int64)), dtype=np.int64)
            if ids_b.size == 0:
                continue
            shared = np.intersect1d(ids_a, ids_b, assume_unique=True)
            if int(shared.size) < threshold:
                continue
            centroid_b = centroids.get(region_b, np.zeros(3, dtype=float))
            shared_pts = points[shared]
            bounds_min = np.min(shared_pts, axis=0) if shared_pts.size else np.zeros(3, dtype=float)
            bounds_max = np.max(shared_pts, axis=0) if shared_pts.size else np.zeros(3, dtype=float)
            out.append(
                RegionAdjacencyInfo(
                    region_a=str(region_a),
                    region_b=str(region_b),
                    shared_point_ids=tuple(int(v) for v in shared.tolist()),
                    shared_point_count=int(shared.size),
                    centroid_distance=float(np.linalg.norm(np.asarray(centroid_a, dtype=float) - np.asarray(centroid_b, dtype=float))),
                    metadata={
                        'shared_bounds_min': tuple(float(v) for v in np.asarray(bounds_min, dtype=float).tolist()),
                        'shared_bounds_max': tuple(float(v) for v in np.asarray(bounds_max, dtype=float).tolist()),
                        'pair_mode': bool(pair_mode),
                    },
                )
            )
    out.sort(key=lambda item: (-item.shared_point_count, item.region_a, item.region_b))
    return tuple(out)


def compute_region_boundary_adjacency(
    model: SimulationModel,
    *,
    selector: Any = None,
    region_names: tuple[str, ...] = (),
    left_selector: Any = None,
    left_region_names: tuple[str, ...] = (),
    right_selector: Any = None,
    right_region_names: tuple[str, ...] = (),
    min_shared_faces: int = 1,
) -> tuple[RegionBoundaryAdjacencyInfo, ...]:
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    region_points = _region_point_ids(model)
    region_cells = _region_cell_ids(model)
    centroids = _compute_region_centroids(points, region_points)
    left, right, pair_mode = _selected_region_pairs(
        model,
        selector=selector,
        region_names=region_names,
        left_selector=left_selector,
        left_region_names=left_region_names,
        right_selector=right_selector,
        right_region_names=right_region_names,
    )
    allowed_pairs: set[tuple[str, str]] = set()
    left_set = set(left)
    right_set = set(right)
    for region_a in left:
        right_iter = right if pair_mode else [item for item in right if item != region_a]
        for region_b in right_iter:
            if region_a == region_b:
                continue
            key = (region_a, region_b) if pair_mode else tuple(sorted((region_a, region_b)))
            allowed_pairs.add(key)
    face_map: dict[tuple[int, ...], list[tuple[str, tuple[int, ...], float]]] = {}
    for region_name, cell_ids in region_cells.items():
        for cid in cell_ids:
            try:
                cell = grid.get_cell(int(cid))
            except Exception:
                continue
            point_ids = tuple(int(v) for v in getattr(cell, 'point_ids', ()))
            if len(point_ids) < 3:
                continue
            faces = _cell_faces_from_point_ids(int(getattr(cell, 'type', -1)), point_ids)
            for face_pts in faces:
                canonical = tuple(sorted(int(v) for v in face_pts))
                if len(canonical) < 3:
                    continue
                area = _polygon_area_3d(points[np.asarray(face_pts, dtype=np.int64)])
                face_map.setdefault(canonical, []).append((region_name, tuple(face_pts), float(area)))
    accum: dict[tuple[str, str], _BoundaryAccumulator] = {}
    for canonical, owners in face_map.items():
        if len(owners) < 2:
            continue
        for idx in range(len(owners)):
            region_a, _, area_a = owners[idx]
            for jdx in range(idx + 1, len(owners)):
                region_b, _, area_b = owners[jdx]
                if region_a == region_b:
                    continue
                if pair_mode:
                    if region_a in left_set and region_b in right_set:
                        key = (region_a, region_b)
                    elif region_b in left_set and region_a in right_set:
                        key = (region_b, region_a)
                    else:
                        continue
                else:
                    key = tuple(sorted((region_a, region_b)))
                if key not in allowed_pairs:
                    continue
                acc = accum.setdefault(key, _BoundaryAccumulator())
                if canonical not in acc.faces:
                    acc.faces.add(canonical)
                    acc.point_ids.update(int(v) for v in canonical)
                    acc.total_face_area += max(float(area_a), float(area_b))
    threshold = max(1, int(min_shared_faces))
    out: list[RegionBoundaryAdjacencyInfo] = []
    for key, acc in accum.items():
        if len(acc.faces) < threshold:
            continue
        region_a, region_b = key
        centroid_a = centroids.get(region_a, np.zeros(3, dtype=float))
        centroid_b = centroids.get(region_b, np.zeros(3, dtype=float))
        boundary_ids = tuple(sorted(int(v) for v in acc.point_ids))
        shared_pts = points[np.asarray(boundary_ids, dtype=np.int64)] if boundary_ids else np.empty((0, 3), dtype=float)
        bounds_min = np.min(shared_pts, axis=0) if shared_pts.size else np.zeros(3, dtype=float)
        bounds_max = np.max(shared_pts, axis=0) if shared_pts.size else np.zeros(3, dtype=float)
        out.append(
            RegionBoundaryAdjacencyInfo(
                region_a=str(region_a),
                region_b=str(region_b),
                shared_face_count=int(len(acc.faces)),
                shared_boundary_point_ids=boundary_ids,
                shared_point_count=int(len(boundary_ids)),
                shared_face_area=float(acc.total_face_area),
                centroid_distance=float(np.linalg.norm(np.asarray(centroid_a, dtype=float) - np.asarray(centroid_b, dtype=float))),
                metadata={
                    'pair_mode': bool(pair_mode),
                    'shared_face_keys': tuple(acc.faces),
                    'shared_bounds_min': tuple(float(v) for v in np.asarray(bounds_min, dtype=float).tolist()),
                    'shared_bounds_max': tuple(float(v) for v in np.asarray(bounds_max, dtype=float).tolist()),
                },
            )
        )
    out.sort(key=lambda item: (-item.shared_face_count, -item.shared_face_area, item.region_a, item.region_b))
    return tuple(out)


def adjacency_summary_rows(adjacencies: tuple[RegionAdjacencyInfo | RegionBoundaryAdjacencyInfo, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in adjacencies:
        base = {
            'region_a': item.region_a,
            'region_b': item.region_b,
            'centroid_distance': float(item.centroid_distance),
            **dict(item.metadata),
        }
        if isinstance(item, RegionBoundaryAdjacencyInfo):
            base.update({
                'shared_face_count': int(item.shared_face_count),
                'shared_point_count': int(item.shared_point_count),
                'shared_face_area': float(item.shared_face_area),
                'shared_boundary_point_ids': tuple(int(v) for v in item.shared_boundary_point_ids),
            })
        else:
            base.update({
                'shared_point_count': int(item.shared_point_count),
                'shared_point_ids': tuple(int(v) for v in item.shared_point_ids),
            })
        rows.append(base)
    return rows
