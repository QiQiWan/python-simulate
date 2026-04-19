
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.pipeline.adjacency import _cell_faces_from_point_ids, _polygon_area_3d
from geoai_simkit.pipeline.selectors import resolve_region_selector


@dataclass(slots=True)
class RegionBoundarySurfaceSummary:
    region_name: str
    face_count: int
    point_ids: tuple[int, ...]
    point_count: int
    total_area: float
    centroid: tuple[float, float, float]
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    external_face_count: int
    interface_face_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RegionSurfaceInterfaceCandidate:
    region_a: str
    region_b: str
    shared_face_count: int
    slave_surface_point_ids: tuple[int, ...]
    master_surface_point_ids: tuple[int, ...]
    shared_boundary_point_ids: tuple[int, ...]
    master_boundary_point_ids: tuple[int, ...]
    shared_face_area: float
    centroid: tuple[float, float, float]
    centroid_distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _FaceRecord:
    face_key: tuple[int, ...]
    point_ids: tuple[int, ...]
    area: float
    centroid: np.ndarray
    regions: tuple[str, ...]


def _select_regions(model: SimulationModel, selector: Any = None, explicit_names: tuple[str, ...] = ()) -> list[str]:
    names: list[str] = []
    if explicit_names:
        names.extend(str(v) for v in explicit_names if str(v))
    if selector is not None:
        names.extend(resolve_region_selector(model, selector))
    if not names:
        names.extend(str(region.name) for region in model.region_tags)
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _region_face_records(model: SimulationModel) -> tuple[dict[str, list[_FaceRecord]], dict[tuple[int, ...], list[tuple[str, tuple[int, ...], float, np.ndarray]]], np.ndarray]:
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    by_region: dict[str, list[_FaceRecord]] = {str(region.name): [] for region in model.region_tags}
    owner_map: dict[tuple[int, ...], list[tuple[str, tuple[int, ...], float, np.ndarray]]] = {}
    for region in model.region_tags:
        region_name = str(region.name)
        for cid in np.asarray(region.cell_ids, dtype=np.int64):
            try:
                cell = grid.get_cell(int(cid))
            except Exception:
                continue
            point_ids = tuple(int(v) for v in getattr(cell, 'point_ids', []))
            for face in _cell_faces_from_point_ids(int(cell.type), point_ids):
                face_ids = tuple(int(v) for v in face)
                face_key = tuple(sorted(face_ids))
                face_points = points[np.asarray(face_ids, dtype=np.int64)] if face_ids else np.empty((0, 3), dtype=float)
                centroid = np.mean(face_points, axis=0) if face_points.size else np.zeros(3, dtype=float)
                area = _polygon_area_3d(face_points)
                owner_map.setdefault(face_key, []).append((region_name, face_ids, float(area), np.asarray(centroid, dtype=float)))
    for face_key, owners in owner_map.items():
        region_counts: dict[str, int] = {}
        for region_name, _, _, _ in owners:
            region_counts[region_name] = region_counts.get(region_name, 0) + 1
        region_labels = tuple(sorted(region_counts))
        for region_name, point_ids, area, centroid in owners:
            if region_counts.get(region_name, 0) != 1:
                continue
            by_region.setdefault(region_name, []).append(_FaceRecord(face_key=face_key, point_ids=tuple(int(v) for v in point_ids), area=float(area), centroid=np.asarray(centroid, dtype=float), regions=region_labels))
    return by_region, owner_map, points


def compute_region_boundary_surfaces(
    model: SimulationModel,
    *,
    selector: Any = None,
    region_names: tuple[str, ...] = (),
) -> tuple[RegionBoundarySurfaceSummary, ...]:
    selected = set(_select_regions(model, selector=selector, explicit_names=region_names))
    by_region, _, points = _region_face_records(model)
    out: list[RegionBoundarySurfaceSummary] = []
    for region_name in sorted(selected):
        records = by_region.get(region_name, [])
        point_ids = sorted({int(pid) for record in records for pid in record.point_ids})
        area = float(sum(float(record.area) for record in records))
        if records:
            centroids = np.asarray([record.centroid for record in records], dtype=float)
            weights = np.asarray([max(float(record.area), 1.0e-12) for record in records], dtype=float)
            centroid = tuple(float(v) for v in np.average(centroids, axis=0, weights=weights).tolist())
        else:
            centroid = (0.0, 0.0, 0.0)
        pts = points[np.asarray(point_ids, dtype=np.int64)] if point_ids else np.empty((0, 3), dtype=float)
        bounds_min = tuple(float(v) for v in (np.min(pts, axis=0) if pts.size else np.zeros(3, dtype=float)).tolist())
        bounds_max = tuple(float(v) for v in (np.max(pts, axis=0) if pts.size else np.zeros(3, dtype=float)).tolist())
        external_face_count = sum(1 for record in records if len(record.regions) == 1)
        interface_face_count = sum(1 for record in records if len(record.regions) > 1)
        out.append(RegionBoundarySurfaceSummary(
            region_name=region_name,
            face_count=len(records),
            point_ids=tuple(point_ids),
            point_count=len(point_ids),
            total_area=area,
            centroid=centroid,
            bounds_min=bounds_min,
            bounds_max=bounds_max,
            external_face_count=external_face_count,
            interface_face_count=interface_face_count,
            metadata={'surface_kind': 'region_boundary', 'has_interface_boundary': bool(interface_face_count > 0)},
        ))
    return tuple(out)


def compute_region_surface_interface_candidates(
    model: SimulationModel,
    *,
    selector: Any = None,
    region_names: tuple[str, ...] = (),
    left_selector: Any = None,
    left_region_names: tuple[str, ...] = (),
    right_selector: Any = None,
    right_region_names: tuple[str, ...] = (),
    min_shared_faces: int = 1,
) -> tuple[RegionSurfaceInterfaceCandidate, ...]:
    region_surface_map = {item.region_name: item for item in compute_region_boundary_surfaces(model)}
    by_region, owner_map, points = _region_face_records(model)
    if left_selector is not None or left_region_names:
        left = _select_regions(model, selector=left_selector, explicit_names=left_region_names)
        right = _select_regions(model, selector=right_selector, explicit_names=right_region_names)
        pair_mode = True
    else:
        selected = _select_regions(model, selector=selector, explicit_names=region_names)
        left = selected
        right = selected
        pair_mode = False
    allowed_left = set(left)
    allowed_right = set(right)
    pair_faces: dict[tuple[str, str], list[tuple[tuple[int, ...], float, np.ndarray]]] = {}
    for face_key, owners in owner_map.items():
        unique_regions = sorted({region_name for region_name, _, _, _ in owners})
        if len(unique_regions) < 2:
            continue
        for idx, region_a in enumerate(unique_regions):
            for region_b in unique_regions[idx + 1:]:
                if pair_mode:
                    ordered: tuple[str, str] | None = None
                    if region_a in allowed_left and region_b in allowed_right:
                        ordered = (region_a, region_b)
                    elif region_b in allowed_left and region_a in allowed_right:
                        ordered = (region_b, region_a)
                    if ordered is None:
                        continue
                    key = ordered
                else:
                    if region_a not in allowed_left or region_b not in allowed_right:
                        continue
                    key = tuple(sorted((region_a, region_b)))
                face_points = points[np.asarray(face_key, dtype=np.int64)] if face_key else np.empty((0, 3), dtype=float)
                centroid = np.mean(face_points, axis=0) if face_points.size else np.zeros(3, dtype=float)
                area = _polygon_area_3d(face_points)
                pair_faces.setdefault(key, []).append((face_key, float(area), np.asarray(centroid, dtype=float)))
    out: list[RegionSurfaceInterfaceCandidate] = []
    threshold = max(1, int(min_shared_faces))
    for key, faces in pair_faces.items():
        region_a, region_b = key
        if len(faces) < threshold:
            continue
        shared_point_ids = sorted({int(pid) for face_key, _, _ in faces for pid in face_key})
        area = float(sum(face_area for _, face_area, _ in faces))
        centroids = np.asarray([face_centroid for _, _, face_centroid in faces], dtype=float)
        weights = np.asarray([max(face_area, 1.0e-12) for _, face_area, _ in faces], dtype=float)
        centroid = tuple(float(v) for v in np.average(centroids, axis=0, weights=weights).tolist()) if len(faces) else (0.0, 0.0, 0.0)
        surf_a = region_surface_map.get(region_a)
        surf_b = region_surface_map.get(region_b)
        centroid_a = np.asarray(surf_a.centroid if surf_a is not None else centroid, dtype=float)
        centroid_b = np.asarray(surf_b.centroid if surf_b is not None else centroid, dtype=float)
        out.append(RegionSurfaceInterfaceCandidate(
            region_a=region_a,
            region_b=region_b,
            shared_face_count=len(faces),
            slave_surface_point_ids=tuple(int(v) for v in shared_point_ids),
            master_surface_point_ids=tuple(int(v) for v in shared_point_ids),
            shared_boundary_point_ids=tuple(int(v) for v in shared_point_ids),
            master_boundary_point_ids=tuple(int(v) for v in ((surf_b.point_ids if surf_b is not None else tuple(shared_point_ids)))),
            shared_face_area=area,
            centroid=centroid,
            centroid_distance=float(np.linalg.norm(centroid_a - centroid_b)),
            metadata={
                'pair_mode': bool(pair_mode),
                'shared_face_area': area,
                'shared_face_count': len(faces),
                'shared_point_count': len(shared_point_ids),
            },
        ))
    out.sort(key=lambda item: (-item.shared_face_count, -item.shared_face_area, item.region_a, item.region_b))
    return tuple(out)


def region_surface_summary_rows(items: tuple[RegionBoundarySurfaceSummary, ...] | list[RegionBoundarySurfaceSummary]) -> list[dict[str, Any]]:
    return [
        {
            'region_name': item.region_name,
            'face_count': int(item.face_count),
            'point_count': int(item.point_count),
            'total_area': float(item.total_area),
            'external_face_count': int(item.external_face_count),
            'interface_face_count': int(item.interface_face_count),
            'centroid': [float(v) for v in item.centroid],
            'bounds_min': [float(v) for v in item.bounds_min],
            'bounds_max': [float(v) for v in item.bounds_max],
        }
        for item in items
    ]


def interface_candidate_summary_rows(items: tuple[RegionSurfaceInterfaceCandidate, ...] | list[RegionSurfaceInterfaceCandidate]) -> list[dict[str, Any]]:
    return [
        {
            'region_a': item.region_a,
            'region_b': item.region_b,
            'shared_face_count': int(item.shared_face_count),
            'shared_face_area': float(item.shared_face_area),
            'shared_point_count': int(len(item.shared_boundary_point_ids)),
            'centroid': [float(v) for v in item.centroid],
            'centroid_distance': float(item.centroid_distance),
        }
        for item in items
    ]
