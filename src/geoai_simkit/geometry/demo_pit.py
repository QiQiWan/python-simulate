from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from geoai_simkit.core.model import AnalysisStage, InterfaceDefinition, SimulationModel, StructuralElementDefinition


@dataclass(frozen=True, slots=True)
class DemoPitStageMaps:
    initial: dict[str, bool]
    excavate_level_1: dict[str, bool]
    excavate_level_2: dict[str, bool]


@dataclass(frozen=True, slots=True)
class DemoCouplingSummary:
    wall_mode: str
    interface_count: int
    structure_count: int
    support_groups: tuple[str, ...]


AUTO_WALL_SOURCE = 'parametric_pit_auto_wall'
AUTO_SUPPORT_SOURCE = 'parametric_pit_auto_support'

DEMO_INTERFACE_POLICIES: dict[str, str] = {
    'manual_like_nearest_soil': '优先共点，缺失时自动吸附到最近土层节点',
    'exact_only': '仅使用共点匹配，不执行最近土层吸附',
    'nearest_soil_relaxed': '优先共点，并扩大最近土层吸附半径',
}
DEMO_INTERFACE_GROUPS: dict[str, str] = {
    'outer': '墙外侧与保留土体的界面',
    'inner_upper': '上部开挖层与墙内侧的界面',
    'inner_lower': '下部开挖层与墙内侧的界面',
}
DEMO_SUPPORT_GROUPS: dict[str, str] = {
    'crown_beam': '顶部冠梁',
    'strut_level_1': '第一道支撑',
    'strut_level_2': '第二道支撑',
}
DEMO_INTERFACE_REGION_OVERRIDES: dict[str, str] = {
    'auto': '自动选择最近土层',
    'soil_mass': '优先匹配 soil_mass',
    'soil_excavation_1': '优先匹配 soil_excavation_1',
    'soil_excavation_2': '优先匹配 soil_excavation_2',
}
DEMO_SOLVER_PRESETS: dict[str, str] = {
    'conservative': '保守：更小增量、更多切回，优先稳定收敛',
    'balanced': '平衡：默认推荐，兼顾稳定性与速度',
    'aggressive': '激进：更大增量、较少切回，优先速度',
}

_DEMO_SOLVER_PRESET_PAYLOADS: dict[str, dict[str, dict[str, float | int | bool]]] = {
    'conservative': {
        'coupled': {
            'initial_increment': 0.00625,
            'max_iterations': 48,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.00625,
            'min_load_increment': 0.00078125,
            'max_cutbacks': 10,
            'modified_newton_max_reuse': 0,
            'stagnation_patience': 4,
            'stagnation_improvement_tol': 0.005,
            'line_search_trigger_ratio': 0.92,
            'line_search_correction_ratio': 0.06,
        },
        'uncoupled': {
            'initial_increment': 0.025,
            'max_iterations': 36,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.025,
            'min_load_increment': 0.003125,
            'max_cutbacks': 8,
            'modified_newton_max_reuse': 0,
            'stagnation_patience': 3,
            'stagnation_improvement_tol': 0.015,
            'line_search_trigger_ratio': 0.82,
            'line_search_correction_ratio': 0.12,
        },
    },
    'balanced': {
        'coupled': {
            'initial_increment': 0.0125,
            'max_iterations': 40,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.0125,
            'min_load_increment': 0.0015625,
            'max_cutbacks': 8,
            'modified_newton_max_reuse': 0,
            'stagnation_patience': 3,
            'stagnation_improvement_tol': 0.01,
            'line_search_trigger_ratio': 0.85,
            'line_search_correction_ratio': 0.10,
        },
        'uncoupled': {
            'initial_increment': 0.05,
            'max_iterations': 32,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.05,
            'min_load_increment': 0.00625,
            'max_cutbacks': 6,
            'modified_newton_max_reuse': 1,
            'stagnation_patience': 2,
            'stagnation_improvement_tol': 0.02,
            'line_search_trigger_ratio': 0.70,
            'line_search_correction_ratio': 0.20,
        },
    },
    'aggressive': {
        'coupled': {
            'initial_increment': 0.025,
            'max_iterations': 32,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.025,
            'min_load_increment': 0.003125,
            'max_cutbacks': 5,
            'modified_newton_max_reuse': 1,
            'stagnation_patience': 2,
            'stagnation_improvement_tol': 0.015,
            'line_search_trigger_ratio': 0.78,
            'line_search_correction_ratio': 0.16,
        },
        'uncoupled': {
            'initial_increment': 0.10,
            'max_iterations': 28,
            'line_search': True,
            'compute_profile': 'cpu-safe',
            'max_load_fraction_per_step': 0.10,
            'min_load_increment': 0.0125,
            'max_cutbacks': 4,
            'modified_newton_max_reuse': 1,
            'stagnation_patience': 2,
            'stagnation_improvement_tol': 0.03,
            'line_search_trigger_ratio': 0.65,
            'line_search_correction_ratio': 0.25,
        },
    },
}


def interface_policy_options() -> dict[str, str]:
    return dict(DEMO_INTERFACE_POLICIES)


def interface_group_options() -> dict[str, str]:
    return dict(DEMO_INTERFACE_GROUPS)


def support_group_options() -> dict[str, str]:
    return dict(DEMO_SUPPORT_GROUPS)


def interface_region_override_options() -> dict[str, str]:
    return dict(DEMO_INTERFACE_REGION_OVERRIDES)


def solver_preset_options() -> dict[str, str]:
    return dict(DEMO_SOLVER_PRESETS)


def normalize_solver_preset(preset: str | None) -> str:
    key = str(preset or 'balanced').strip().lower()
    return key if key in DEMO_SOLVER_PRESETS else 'balanced'


def explain_solver_preset(preset: str | None) -> str:
    return DEMO_SOLVER_PRESETS[normalize_solver_preset(preset)]


def demo_solver_preset_payload(preset: str | None, *, coupled: bool) -> dict[str, float | int | bool]:
    key = normalize_solver_preset(preset)
    return dict(_DEMO_SOLVER_PRESET_PAYLOADS[key]['coupled' if coupled else 'uncoupled'])


def apply_demo_solver_preset(metadata: dict[str, object] | None, preset: str | None, *, coupled: bool) -> dict[str, object]:
    out: dict[str, object] = dict(metadata or {})
    key = normalize_solver_preset(preset)
    out.update(demo_solver_preset_payload(key, coupled=coupled))
    out['solver_preset'] = key
    out['solver_preset_label'] = explain_solver_preset(key)
    out['coupled_demo_stage'] = bool(coupled)
    return out


def normalize_interface_policy(policy: str | None) -> str:
    key = str(policy or 'manual_like_nearest_soil').strip()
    if key in DEMO_INTERFACE_POLICIES:
        return key
    return 'manual_like_nearest_soil'


def explain_interface_policy(policy: str | None) -> str:
    return DEMO_INTERFACE_POLICIES[normalize_interface_policy(policy)]


def _normalize_enabled_groups(raw: object, allowed: dict[str, str]) -> tuple[str, ...]:
    if isinstance(raw, str):
        items = [part.strip() for part in raw.replace(';', ',').split(',') if part.strip()]
    elif isinstance(raw, (list, tuple, set)):
        items = [str(part).strip() for part in raw if str(part).strip()]
    else:
        items = []
    normalized = tuple(name for name in allowed if name in items)
    if normalized:
        return normalized
    return tuple(allowed)


def normalize_enabled_interface_groups(raw: object) -> tuple[str, ...]:
    return _normalize_enabled_groups(raw, DEMO_INTERFACE_GROUPS)


def normalize_enabled_support_groups(raw: object) -> tuple[str, ...]:
    return _normalize_enabled_groups(raw, DEMO_SUPPORT_GROUPS)


def normalize_interface_region_overrides(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for group in DEMO_INTERFACE_GROUPS:
        value = str(raw.get(group) or '').strip()
        if value and value in DEMO_INTERFACE_REGION_OVERRIDES and value != 'auto':
            out[group] = value
    return out


def enabled_interface_region_overrides(model: SimulationModel) -> dict[str, str]:
    return normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides'))


def _merge_preferred_regions(defaults: tuple[str, ...], override: str | None, available: dict[str, np.ndarray]) -> tuple[str, ...]:
    ordered: list[str] = []
    if override and override in available and np.asarray(available.get(override, np.empty((0,), dtype=np.int64))).size > 0:
        ordered.append(override)
    for name in defaults:
        if name in available and name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def enabled_interface_groups(model: SimulationModel) -> tuple[str, ...]:
    return normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups'))


def enabled_support_groups(model: SimulationModel) -> tuple[str, ...]:
    return normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups'))


def build_demo_stage_maps(model: SimulationModel, *, wall_active: bool) -> DemoPitStageMaps:
    activation = {region.name: False for region in model.region_tags}
    for name in ('soil_mass', 'soil_excavation_1', 'soil_excavation_2'):
        if model.get_region(name) is not None:
            activation[name] = True
    if model.get_region('wall') is not None:
        activation['wall'] = bool(wall_active)
    stage1 = dict(activation)
    if 'soil_excavation_1' in stage1:
        stage1['soil_excavation_1'] = False
    stage2 = dict(stage1)
    if 'soil_excavation_2' in stage2:
        stage2['soil_excavation_2'] = False
    return DemoPitStageMaps(initial=activation, excavate_level_1=stage1, excavate_level_2=stage2)


def _coord_key(point: np.ndarray, *, scale: float) -> tuple[int, int, int]:
    return tuple(int(v) for v in np.round(np.asarray(point, dtype=float) / max(scale, 1.0e-9)))


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
        out[region.name] = np.asarray(sorted(pids), dtype=np.int64)
    return out


def _build_point_map(points: np.ndarray, point_ids: np.ndarray, *, scale: float) -> dict[tuple[int, int, int], list[int]]:
    mapping: dict[tuple[int, int, int], list[int]] = {}
    for pid in np.asarray(point_ids, dtype=np.int64):
        key = _coord_key(points[int(pid)], scale=scale)
        mapping.setdefault(key, []).append(int(pid))
    return mapping


def _estimate_reference_spacing(points: np.ndarray, point_ids: np.ndarray) -> float:
    point_ids = np.asarray(point_ids, dtype=np.int64)
    if point_ids.size < 2:
        return 1.0
    pts = np.asarray(points[point_ids], dtype=float)
    spacings: list[float] = []
    for axis in range(min(3, pts.shape[1])):
        coords = np.unique(np.round(pts[:, axis], decimals=9))
        if coords.size < 2:
            continue
        diffs = np.diff(np.sort(coords))
        diffs = diffs[np.abs(diffs) > 1.0e-9]
        if diffs.size:
            spacings.append(float(np.min(diffs)))
    if not spacings:
        return 1.0
    return max(1.0e-6, float(min(spacings)))


def _nearest_pid_from_candidates(
    candidate_ids: np.ndarray,
    points: np.ndarray,
    *,
    target: np.ndarray,
    predicate: Callable[[np.ndarray], bool],
    max_distance: float,
) -> int | None:
    candidate_ids = np.asarray(candidate_ids, dtype=np.int64)
    if candidate_ids.size == 0:
        return None
    target = np.asarray(target, dtype=float)
    best_pid: int | None = None
    best_dist = float('inf')
    for pid in candidate_ids:
        coord = np.asarray(points[int(pid)], dtype=float)
        if not predicate(coord):
            continue
        dist = float(np.linalg.norm(coord - target))
        if dist < best_dist:
            best_dist = dist
            best_pid = int(pid)
    if best_pid is None:
        return None
    if best_dist > max(max_distance, 1.0e-6):
        return None
    return best_pid


@dataclass(frozen=True, slots=True)
class _PairBuildResult:
    slave_ids: tuple[int, ...]
    master_ids: tuple[int, ...]
    matched_regions: tuple[str, ...]
    exact_matches: int
    nearest_matches: int
    unmatched: int
    max_pair_distance: float


def _build_interface_pairs(
    *,
    wall_point_ids: np.ndarray,
    soil_region_points: dict[str, np.ndarray],
    points: np.ndarray,
    scale: float,
    predicate: Callable[[np.ndarray], bool],
    preferred_regions: tuple[str, ...],
    fallback_regions: tuple[str, ...],
    face_hint: str,
    allow_nearest: bool = True,
    nearest_radius_factor: float = 1.75,
) -> _PairBuildResult:
    wall_point_ids = np.asarray(wall_point_ids, dtype=np.int64)
    wall_face_ids = [int(pid) for pid in wall_point_ids if predicate(np.asarray(points[int(pid)], dtype=float))]
    if not wall_face_ids:
        return _PairBuildResult((), (), (), 0, 0, 0, 0.0)

    wall_map = _build_point_map(points, np.asarray(wall_face_ids, dtype=np.int64), scale=scale)
    ref_spacing = _estimate_reference_spacing(points, np.asarray(wall_face_ids, dtype=np.int64))
    exact_radius = max(scale * 0.6, 1.0e-8)
    nearest_radius = max(ref_spacing * max(1.0, float(nearest_radius_factor)), exact_radius * 10.0)

    search_order: list[str] = []
    for name in (*preferred_regions, *fallback_regions):
        if name not in soil_region_points:
            continue
        if name not in search_order:
            search_order.append(name)

    slave: list[int] = []
    master: list[int] = []
    matched_regions: list[str] = []
    exact_matches = 0
    nearest_matches = 0
    unmatched = 0
    max_pair_distance = 0.0
    used_pairs: set[tuple[int, int]] = set()

    for wall_pid in wall_face_ids:
        target = np.asarray(points[int(wall_pid)], dtype=float)
        key = _coord_key(target, scale=scale)
        chosen_master: int | None = None
        chosen_region: str | None = None
        chosen_mode = 'nearest'

        # First try exact coordinate overlap in the preferred order.
        for region_name in search_order:
            region_ids = soil_region_points.get(region_name)
            if region_ids is None or region_ids.size == 0:
                continue
            region_map = _build_point_map(points, region_ids, scale=scale)
            region_pids = region_map.get(key) or []
            if not region_pids:
                continue
            for candidate in region_pids:
                candidate_coord = np.asarray(points[int(candidate)], dtype=float)
                if not predicate(candidate_coord):
                    continue
                if float(np.linalg.norm(candidate_coord - target)) <= exact_radius:
                    chosen_master = int(candidate)
                    chosen_region = region_name
                    chosen_mode = 'exact'
                    break
            if chosen_master is not None:
                break

        if chosen_master is None and allow_nearest:
            for region_name in search_order:
                region_ids = soil_region_points.get(region_name)
                if region_ids is None or region_ids.size == 0:
                    continue
                candidate = _nearest_pid_from_candidates(
                    region_ids,
                    points,
                    target=target,
                    predicate=predicate,
                    max_distance=nearest_radius,
                )
                if candidate is not None:
                    chosen_master = int(candidate)
                    chosen_region = region_name
                    break

        if chosen_master is None or chosen_region is None:
            unmatched += 1
            continue
        pair = (int(wall_pid), int(chosen_master))
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        slave.append(pair[0])
        master.append(pair[1])
        matched_regions.append(chosen_region)
        pair_distance = float(np.linalg.norm(np.asarray(points[pair[0]], dtype=float) - np.asarray(points[pair[1]], dtype=float)))
        max_pair_distance = max(max_pair_distance, pair_distance)
        if chosen_mode == 'exact':
            exact_matches += 1
        else:
            nearest_matches += 1

    return _PairBuildResult(
        tuple(slave),
        tuple(master),
        tuple(sorted(set(matched_regions))),
        exact_matches,
        nearest_matches,
        unmatched,
        max_pair_distance,
    )


def _parametric_scene_payload(model: SimulationModel) -> dict[str, float]:
    payload = dict(model.metadata.get('parametric_scene') or {})
    for key in ('length', 'width', 'depth', 'soil_depth', 'wall_thickness'):
        try:
            payload[key] = float(payload[key])
        except Exception:
            raise ValueError(f'Parametric pit metadata is missing numeric field: {key}')
    return payload


def _nearest_matching_pid(
    point_ids: np.ndarray,
    points: np.ndarray,
    *,
    target: np.ndarray,
    predicate: Callable[[np.ndarray], bool],
    tol: float,
) -> int | None:
    if point_ids.size == 0:
        return None
    candidates: list[tuple[float, int]] = []
    target = np.asarray(target, dtype=float)
    for pid in np.asarray(point_ids, dtype=np.int64):
        coord = np.asarray(points[int(pid)], dtype=float)
        if not predicate(coord):
            continue
        dist = float(np.linalg.norm(coord - target))
        candidates.append((dist, int(pid)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    best_dist, best_pid = candidates[0]
    if best_dist > max(tol, 1.0e-6) * 20.0:
        return None
    return best_pid


def _unique_segments(points: np.ndarray, ordered_ids: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in zip(ordered_ids[:-1], ordered_ids[1:], strict=False):
        if a == b:
            continue
        pa = np.asarray(points[int(a)], dtype=float)
        pb = np.asarray(points[int(b)], dtype=float)
        if float(np.linalg.norm(pa - pb)) <= 1.0e-9:
            continue
        seg = (int(a), int(b))
        if seg not in out and (seg[1], seg[0]) not in out:
            out.append(seg)
    return out


def _inner_top_ring_ids(wall_pids: np.ndarray, points: np.ndarray, *, pit_x: float, pit_y: float, tol: float) -> list[int]:
    z0 = 0.0
    corners = [
        np.array([-pit_x, -pit_y, z0], dtype=float),
        np.array([+pit_x, -pit_y, z0], dtype=float),
        np.array([+pit_x, +pit_y, z0], dtype=float),
        np.array([-pit_x, +pit_y, z0], dtype=float),
    ]

    def on_corner(target: np.ndarray) -> int | None:
        return _nearest_matching_pid(
            wall_pids,
            points,
            target=target,
            predicate=lambda p: abs(float(p[2]) - z0) <= tol,
            tol=tol,
        )

    ids = [on_corner(item) for item in corners]
    if any(item is None for item in ids):
        return []
    return [int(item) for item in ids if item is not None]


def build_demo_wall_interfaces(model: SimulationModel, *, interface_policy: str | None = None) -> list[InterfaceDefinition]:
    if model.metadata.get('source') != 'parametric_pit':
        return []
    if model.get_region('wall') is None:
        return []
    scene = _parametric_scene_payload(model)
    length = float(scene['length'])
    width = float(scene['width'])
    depth = float(scene['depth'])
    thickness = float(scene['wall_thickness'])
    pit_x = length / 2.0
    pit_y = width / 2.0
    tol = max(1.0e-6, 1.0e-6 * max(length, width, depth, thickness))

    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    region_points = _region_point_ids(model)
    wall_pids = region_points.get('wall')
    if wall_pids is None or wall_pids.size == 0:
        return []

    reference_spacing = _estimate_reference_spacing(points, wall_pids)
    scale = max(1.0e-7, min(reference_spacing * 0.25, tol * 50.0))
    interface_policy = normalize_interface_policy(interface_policy or model.metadata.get('demo_interface_auto_policy'))
    allow_nearest = interface_policy != 'exact_only'
    nearest_radius_factor = float(model.metadata.get('demo_interface_nearest_radius_factor') or (2.6 if interface_policy == 'nearest_soil_relaxed' else 1.75))
    enabled_groups = set(enabled_interface_groups(model))
    region_overrides = enabled_interface_region_overrides(model)

    def on_plane_y(value: float) -> Callable[[np.ndarray], bool]:
        return lambda p: abs(float(p[1]) - value) <= max(tol, reference_spacing * 0.35)

    def on_plane_x(value: float) -> Callable[[np.ndarray], bool]:
        return lambda p: abs(float(p[0]) - value) <= max(tol, reference_spacing * 0.35)

    def on_plane_y_strict(value: float) -> Callable[[np.ndarray], bool]:
        return lambda p: on_plane_y(value)(p) and abs(float(p[0])) < pit_x - max(tol, reference_spacing * 0.5)

    def on_plane_x_all(value: float) -> Callable[[np.ndarray], bool]:
        return on_plane_x(value)

    def z_range(z_min: float, z_max: float) -> Callable[[np.ndarray], bool]:
        return lambda p: (float(p[2]) >= z_min - max(tol, reference_spacing * 0.5)) and (float(p[2]) <= z_max + max(tol, reference_spacing * 0.5))

    def both(*predicates: Callable[[np.ndarray], bool]) -> Callable[[np.ndarray], bool]:
        return lambda p: all(fn(p) for fn in predicates)

    all_soil_regions = tuple(name for name in ('soil_mass', 'soil_excavation_1', 'soil_excavation_2') if name in region_points)
    soil_region_points = {name: np.asarray(region_points.get(name, np.empty((0,), dtype=np.int64)), dtype=np.int64) for name in all_soil_regions}

    face_specs = [
        ('outer_xmin', both(on_plane_x_all(-(pit_x + thickness)), z_range(-depth, 0.0)), np.array([-1.0, 0.0, 0.0]), (), 'outer', ('soil_mass',), all_soil_regions),
        ('outer_xmax', both(on_plane_x_all(+(pit_x + thickness)), z_range(-depth, 0.0)), np.array([+1.0, 0.0, 0.0]), (), 'outer', ('soil_mass',), all_soil_regions),
        ('outer_ymin', both(on_plane_y_strict(-(pit_y + thickness)), z_range(-depth, 0.0)), np.array([0.0, -1.0, 0.0]), (), 'outer', ('soil_mass',), all_soil_regions),
        ('outer_ymax', both(on_plane_y_strict(+(pit_y + thickness)), z_range(-depth, 0.0)), np.array([0.0, +1.0, 0.0]), (), 'outer', ('soil_mass',), all_soil_regions),
        ('inner_upper_xmin', both(on_plane_x_all(-pit_x), z_range(-depth / 2.0, 0.0)), np.array([+1.0, 0.0, 0.0]), ('initial',), 'inner_upper', ('soil_excavation_1',), ('soil_excavation_1', 'soil_mass', 'soil_excavation_2')),
        ('inner_upper_xmax', both(on_plane_x_all(+pit_x), z_range(-depth / 2.0, 0.0)), np.array([-1.0, 0.0, 0.0]), ('initial',), 'inner_upper', ('soil_excavation_1',), ('soil_excavation_1', 'soil_mass', 'soil_excavation_2')),
        ('inner_upper_ymin', both(on_plane_y_strict(-pit_y), z_range(-depth / 2.0, 0.0)), np.array([0.0, +1.0, 0.0]), ('initial',), 'inner_upper', ('soil_excavation_1',), ('soil_excavation_1', 'soil_mass', 'soil_excavation_2')),
        ('inner_upper_ymax', both(on_plane_y_strict(+pit_y), z_range(-depth / 2.0, 0.0)), np.array([0.0, -1.0, 0.0]), ('initial',), 'inner_upper', ('soil_excavation_1',), ('soil_excavation_1', 'soil_mass', 'soil_excavation_2')),
        ('inner_lower_xmin', both(on_plane_x_all(-pit_x), z_range(-depth, -depth / 2.0)), np.array([+1.0, 0.0, 0.0]), ('initial', 'excavate_level_1'), 'inner_lower', ('soil_excavation_2',), ('soil_excavation_2', 'soil_mass', 'soil_excavation_1')),
        ('inner_lower_xmax', both(on_plane_x_all(+pit_x), z_range(-depth, -depth / 2.0)), np.array([-1.0, 0.0, 0.0]), ('initial', 'excavate_level_1'), 'inner_lower', ('soil_excavation_2',), ('soil_excavation_2', 'soil_mass', 'soil_excavation_1')),
        ('inner_lower_ymin', both(on_plane_y_strict(-pit_y), z_range(-depth, -depth / 2.0)), np.array([0.0, +1.0, 0.0]), ('initial', 'excavate_level_1'), 'inner_lower', ('soil_excavation_2',), ('soil_excavation_2', 'soil_mass', 'soil_excavation_1')),
        ('inner_lower_ymax', both(on_plane_y_strict(+pit_y), z_range(-depth, -depth / 2.0)), np.array([0.0, -1.0, 0.0]), ('initial', 'excavate_level_1'), 'inner_lower', ('soil_excavation_2',), ('soil_excavation_2', 'soil_mass', 'soil_excavation_1')),
    ]

    interfaces: list[InterfaceDefinition] = []
    selection_modes: set[str] = set()
    total_exact = 0
    total_nearest = 0
    report_rows: list[dict[str, object]] = []

    for name, predicate, normal, active_stages, group, preferred_regions, fallback_regions in face_specs:
        if group not in enabled_groups:
            continue
        override_region = region_overrides.get(group)
        effective_preferred_regions = _merge_preferred_regions(tuple(preferred_regions), override_region, soil_region_points)
        pair_result = _build_interface_pairs(
            wall_point_ids=wall_pids,
            soil_region_points=soil_region_points,
            points=points,
            scale=scale,
            predicate=predicate,
            preferred_regions=tuple(effective_preferred_regions),
            fallback_regions=tuple(fallback_regions),
            face_hint=name,
            allow_nearest=allow_nearest,
            nearest_radius_factor=nearest_radius_factor,
        )
        if not pair_result.slave_ids or not pair_result.master_ids:
            continue
        if pair_result.nearest_matches > 0:
            selection_modes.add('nearest_soil_auto')
        if pair_result.exact_matches > 0:
            selection_modes.add('exact_overlap')
        total_exact += int(pair_result.exact_matches)
        total_nearest += int(pair_result.nearest_matches)
        report_rows.append({
            'name': name,
            'group': group,
            'group_label': DEMO_INTERFACE_GROUPS.get(group, group),
            'active_stages': list(active_stages),
            'matched_regions': list(pair_result.matched_regions),
            'preferred_regions': list(effective_preferred_regions),
            'preferred_region_override': str(override_region or ''),
            'selection_mode': 'nearest_soil_auto' if pair_result.nearest_matches > 0 else 'exact_overlap',
            'exact_match_count': int(pair_result.exact_matches),
            'nearest_match_count': int(pair_result.nearest_matches),
            'pair_count': int(len(pair_result.slave_ids)),
            'unmatched_wall_points': int(pair_result.unmatched),
            'max_pair_distance': float(pair_result.max_pair_distance),
        })
        interfaces.append(
            InterfaceDefinition(
                name=f'pit_{name}',
                kind='node_pair',
                slave_point_ids=pair_result.slave_ids,
                master_point_ids=pair_result.master_ids,
                parameters={
                    'kn': 5.0e8,
                    'ks': 1.0e8,
                    'friction_deg': 25.0,
                    'normal': tuple(float(v) for v in np.asarray(normal, dtype=float)),
                    'auto_selection_radius': float(max(reference_spacing * 1.75, tol * 10.0)),
                },
                active_stages=tuple(active_stages),
                metadata={
                    'source': AUTO_WALL_SOURCE,
                    'wall_contact_group': group,
                    'contact_face': name,
                    'slave_region': 'wall',
                    'matched_regions': list(pair_result.matched_regions),
                    'preferred_regions': list(effective_preferred_regions),
            'preferred_region_override': str(override_region or ''),
                    'selection_mode': 'nearest_soil_auto' if pair_result.nearest_matches > 0 else 'exact_overlap',
                    'exact_match_count': int(pair_result.exact_matches),
                    'nearest_match_count': int(pair_result.nearest_matches),
                    'unmatched_wall_points': int(pair_result.unmatched),
                    'max_pair_distance': float(pair_result.max_pair_distance),
                    'plaxis_like_node_pair': True,
                    'plaxis_manual_like_auto': True,
                },
            )
        )

    model.metadata['demo_interface_report'] = report_rows
    model.metadata['demo_interface_auto_policy'] = interface_policy
    model.metadata['demo_interface_auto_policy_label'] = explain_interface_policy(interface_policy)
    if interfaces:
        model.metadata['demo_interface_selection_modes'] = sorted(selection_modes) if selection_modes else ['exact_overlap']
        model.metadata['demo_interface_exact_pairs'] = int(total_exact)
        model.metadata['demo_interface_nearest_pairs'] = int(total_nearest)
        model.metadata['demo_interface_max_pair_distance'] = float(max((float(row['max_pair_distance']) for row in report_rows), default=0.0))
    else:
        model.metadata['demo_interface_selection_modes'] = []
        model.metadata['demo_interface_exact_pairs'] = 0
        model.metadata['demo_interface_nearest_pairs'] = 0
        model.metadata['demo_interface_max_pair_distance'] = 0.0
    return interfaces


def build_demo_support_structures(model: SimulationModel) -> list[StructuralElementDefinition]:
    if model.metadata.get('source') != 'parametric_pit' or model.get_region('wall') is None:
        return []
    scene = _parametric_scene_payload(model)
    length = float(scene['length'])
    width = float(scene['width'])
    depth = float(scene['depth'])
    pit_x = length / 2.0
    pit_y = width / 2.0
    tol = max(1.0e-6, 1.0e-6 * max(length, width, depth))

    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    region_points = _region_point_ids(model)
    wall_pids = region_points.get('wall', np.empty((0,), dtype=np.int64))
    if wall_pids.size == 0:
        return []

    structures: list[StructuralElementDefinition] = []
    seen: set[tuple[str, tuple[int, ...]]] = set()
    enabled_groups = set(enabled_support_groups(model))

    ring_ids = _inner_top_ring_ids(wall_pids, points, pit_x=pit_x, pit_y=pit_y, tol=tol)
    if 'crown_beam' in enabled_groups and len(ring_ids) == 4:
        ring_loop = ring_ids + [ring_ids[0]]
        for idx, (a, b) in enumerate(_unique_segments(points, ring_loop), start=1):
            key = ('crown_beam', tuple(sorted((a, b))))
            if key in seen:
                continue
            seen.add(key)
            structures.append(
                StructuralElementDefinition(
                    name=f'crown_beam_{idx}',
                    kind='truss2',
                    point_ids=(int(a), int(b)),
                    parameters={
                        'E': 2.1e11,
                        'A': 3.5e-2,
                    },
                    active_stages=('initial', 'excavate_level_1', 'excavate_level_2'),
                    metadata={
                        'source': AUTO_SUPPORT_SOURCE,
                        'support_group': 'crown_beam',
                        'role': 'support',
                        'solver_compatible_kind': 'truss2',
                        'design_intent': 'crown_beam',
                    },
                )
            )

    level_specs = [
        ('strut_level_1', -depth * 0.25, ('excavate_level_1', 'excavate_level_2')),
        ('strut_level_2', -depth * 0.75, ('excavate_level_2',)),
    ]

    def on_x_face(value: float, z_target: float) -> Callable[[np.ndarray], bool]:
        return lambda p: abs(float(p[0]) - value) <= tol and abs(float(p[1])) <= tol and abs(float(p[2]) - z_target) <= tol * 8.0

    def on_y_face(value: float, z_target: float) -> Callable[[np.ndarray], bool]:
        return lambda p: abs(float(p[1]) - value) <= tol and abs(float(p[0])) <= tol and abs(float(p[2]) - z_target) <= tol * 8.0

    for group, z_level, active_stages in level_specs:
        if group not in enabled_groups:
            continue
        pairs = [
            (
                _nearest_matching_pid(wall_pids, points, target=np.array([-pit_x, 0.0, z_level]), predicate=on_x_face(-pit_x, z_level), tol=tol),
                _nearest_matching_pid(wall_pids, points, target=np.array([+pit_x, 0.0, z_level]), predicate=on_x_face(+pit_x, z_level), tol=tol),
            ),
            (
                _nearest_matching_pid(wall_pids, points, target=np.array([0.0, -pit_y, z_level]), predicate=on_y_face(-pit_y, z_level), tol=tol),
                _nearest_matching_pid(wall_pids, points, target=np.array([0.0, +pit_y, z_level]), predicate=on_y_face(+pit_y, z_level), tol=tol),
            ),
        ]
        for idx, pair in enumerate(pairs, start=1):
            a, b = pair
            if a is None or b is None or int(a) == int(b):
                continue
            key = (group, tuple(sorted((int(a), int(b)))))
            if key in seen:
                continue
            seen.add(key)
            structures.append(
                StructuralElementDefinition(
                    name=f'{group}_{idx}',
                    kind='truss2',
                    point_ids=(int(a), int(b)),
                    parameters={
                        'E': 2.05e11,
                        'A': 5.0e-3,
                        'prestress': 2.5e5,
                    },
                    active_stages=tuple(active_stages),
                    metadata={
                        'source': AUTO_SUPPORT_SOURCE,
                        'support_group': group,
                        'role': 'support',
                        'plaxis_like_strut': True,
                    },
                )
            )
    return structures


def expected_wall_contact_groups_for_stage(stage_name: str, enabled_groups: tuple[str, ...] | None = None) -> set[str]:
    lowered = str(stage_name).lower()
    if lowered == 'initial':
        required = {'outer', 'inner_upper', 'inner_lower'}
    elif 'level_1' in lowered or lowered.endswith('_1'):
        required = {'outer', 'inner_lower'}
    elif 'level_2' in lowered or lowered.endswith('_2'):
        required = {'outer'}
    else:
        required = {'outer'}
    if enabled_groups is None:
        return required
    return required & set(enabled_groups)


def expected_support_groups_for_stage(stage_name: str, enabled_groups: tuple[str, ...] | None = None) -> set[str]:
    lowered = str(stage_name).lower()
    if lowered == 'initial':
        required = {'crown_beam'}
    elif 'level_1' in lowered or lowered.endswith('_1'):
        required = {'crown_beam', 'strut_level_1'}
    elif 'level_2' in lowered or lowered.endswith('_2'):
        required = {'crown_beam', 'strut_level_1', 'strut_level_2'}
    else:
        required = {'crown_beam'}
    if enabled_groups is None:
        return required
    return required & set(enabled_groups)


def demo_interface_report_rows(model: SimulationModel) -> list[dict[str, object]]:
    rows = model.metadata.get('demo_interface_report') or []
    if isinstance(rows, list):
        return [dict(item) for item in rows if isinstance(item, dict)]
    return []


def coupling_wizard_summary(model: SimulationModel) -> dict[str, object]:
    report = demo_interface_report_rows(model)
    return {
        'wall_mode': str(model.metadata.get('demo_wall_mode') or 'display_only'),
        'interface_policy': normalize_interface_policy(model.metadata.get('demo_interface_auto_policy')),
        'solver_preset': normalize_solver_preset(model.metadata.get('demo_solver_preset')),
        'solver_preset_label': explain_solver_preset(model.metadata.get('demo_solver_preset')),
        'interface_policy_label': explain_interface_policy(model.metadata.get('demo_interface_auto_policy')),
        'selection_modes': list(model.metadata.get('demo_interface_selection_modes') or []),
        'exact_pairs': int(model.metadata.get('demo_interface_exact_pairs') or 0),
        'nearest_pairs': int(model.metadata.get('demo_interface_nearest_pairs') or 0),
        'max_pair_distance': float(model.metadata.get('demo_interface_max_pair_distance') or 0.0),
        'nearest_radius_factor': float(model.metadata.get('demo_interface_nearest_radius_factor') or 0.0),
        'interface_count': int(model.metadata.get('demo_auto_interface_count') or 0),
        'structure_count': int(model.metadata.get('demo_auto_structure_count') or 0),
        'support_groups': list(model.metadata.get('demo_support_groups') or []),
        'enabled_interface_groups': list(enabled_interface_groups(model)),
        'enabled_support_groups': list(enabled_support_groups(model)),
        'interface_region_overrides': dict(enabled_interface_region_overrides(model)),
        'report_rows': report,
    }

def summarize_demo_coupling(model: SimulationModel) -> DemoCouplingSummary:
    interfaces = [item for item in model.interfaces if item.metadata.get('source') == AUTO_WALL_SOURCE]
    structures = [item for item in model.structures if item.metadata.get('source') == AUTO_SUPPORT_SOURCE]
    groups = sorted({str(item.metadata.get('support_group')) for item in structures if item.metadata.get('support_group')})
    return DemoCouplingSummary(
        wall_mode=str(model.metadata.get('demo_wall_mode') or 'display_only'),
        interface_count=len(interfaces),
        structure_count=len(structures),
        support_groups=tuple(groups),
    )


def configure_demo_coupling(
    model: SimulationModel,
    *,
    prefer_wall_solver: bool = True,
    auto_supports: bool = True,
    interface_policy: str | None = None,
) -> str:
    model.interfaces = [iface for iface in model.interfaces if iface.metadata.get('source') != AUTO_WALL_SOURCE]
    model.structures = [item for item in model.structures if item.metadata.get('source') != AUTO_SUPPORT_SOURCE]

    if model.get_region('wall') is None:
        model.metadata['demo_wall_mode'] = 'no_wall'
        model.metadata['demo_auto_interface_count'] = 0
        model.metadata['demo_auto_structure_count'] = 0
        model.metadata['demo_support_groups'] = []
        model.metadata['demo_interface_selection_modes'] = []
        model.metadata['demo_interface_auto_policy'] = normalize_interface_policy(interface_policy)
        model.metadata['demo_interface_auto_policy_label'] = explain_interface_policy(interface_policy)
        model.metadata['demo_enabled_interface_groups'] = list(normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups')))
        model.metadata['demo_enabled_support_groups'] = list(normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups')))
        model.metadata['demo_interface_region_overrides'] = dict(normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides')))
        return 'no_wall'
    if not prefer_wall_solver:
        model.metadata['demo_wall_mode'] = 'display_only'
        model.metadata['demo_auto_interface_count'] = 0
        model.metadata['demo_auto_structure_count'] = 0
        model.metadata['demo_support_groups'] = []
        model.metadata['demo_interface_selection_modes'] = []
        model.metadata['demo_interface_auto_policy'] = normalize_interface_policy(interface_policy)
        model.metadata['demo_interface_auto_policy_label'] = explain_interface_policy(interface_policy)
        model.metadata['demo_enabled_interface_groups'] = list(normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups')))
        model.metadata['demo_enabled_support_groups'] = list(normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups')))
        model.metadata['demo_interface_region_overrides'] = dict(normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides')))
        return 'display_only'

    interface_policy = normalize_interface_policy(interface_policy or model.metadata.get('demo_interface_auto_policy'))
    model.metadata['demo_enabled_interface_groups'] = list(normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups')))
    model.metadata['demo_enabled_support_groups'] = list(normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups')))
    model.metadata['demo_interface_region_overrides'] = dict(normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides')))
    auto_ifaces = build_demo_wall_interfaces(model, interface_policy=interface_policy)
    if not auto_ifaces:
        model.metadata['demo_wall_mode'] = 'display_only'
        model.metadata['demo_auto_interface_count'] = 0
        model.metadata['demo_auto_structure_count'] = 0
        model.metadata['demo_support_groups'] = []
        model.metadata['demo_interface_selection_modes'] = []
        model.metadata['demo_interface_auto_policy'] = normalize_interface_policy(interface_policy)
        model.metadata['demo_interface_auto_policy_label'] = explain_interface_policy(interface_policy)
        model.metadata['demo_enabled_interface_groups'] = list(normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups')))
        model.metadata['demo_enabled_support_groups'] = list(normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups')))
        model.metadata['demo_interface_region_overrides'] = dict(normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides')))
        return 'display_only'

    model.interfaces.extend(auto_ifaces)
    wall_mode = 'auto_interface'
    if auto_supports:
        structures = build_demo_support_structures(model)
        if structures:
            model.structures.extend(structures)
            wall_mode = 'plaxis_like_auto'
    model.metadata['demo_wall_mode'] = wall_mode
    summary = summarize_demo_coupling(model)
    model.metadata['demo_auto_interface_count'] = summary.interface_count
    model.metadata['demo_auto_structure_count'] = summary.structure_count
    model.metadata['demo_support_groups'] = list(summary.support_groups)
    if not model.metadata.get('demo_interface_nearest_radius_factor'):
        model.metadata['demo_interface_nearest_radius_factor'] = 2.6 if interface_policy == 'nearest_soil_relaxed' else 1.75
    return wall_mode


def configure_demo_wall_mode(model: SimulationModel, *, prefer_wall_solver: bool = True, interface_policy: str | None = None) -> str:
    return configure_demo_coupling(model, prefer_wall_solver=prefer_wall_solver, auto_supports=False, interface_policy=interface_policy)


def build_demo_stages(model: SimulationModel, *, wall_active: bool) -> list[AnalysisStage]:
    stage_maps = build_demo_stage_maps(model, wall_active=wall_active)
    wall_mode = str(model.metadata.get('demo_wall_mode') or ('auto_interface' if wall_active else 'display_only'))
    coupled_mode = wall_active and wall_mode in {'auto_interface', 'plaxis_like_auto'}
    solver_preset = normalize_solver_preset(model.metadata.get('demo_solver_preset'))
    common_meta = apply_demo_solver_preset({
        'plaxis_like_staged': True,
        'interface_auto_policy': str(model.metadata.get('demo_interface_auto_policy') or 'manual_like_nearest_soil'),
        'interface_region_overrides': dict(normalize_interface_region_overrides(model.metadata.get('demo_interface_region_overrides'))),
    }, solver_preset, coupled=coupled_mode)
    initial_steps = 8 if coupled_mode else 4
    excavation_steps = 10 if coupled_mode else 6
    enabled_ifaces = normalize_enabled_interface_groups(model.metadata.get('demo_enabled_interface_groups'))
    enabled_supports = normalize_enabled_support_groups(model.metadata.get('demo_enabled_support_groups'))

    def _stage_meta(stage_name: str, activation_map: dict[str, bool]) -> dict[str, object]:
        meta = {
            **common_meta,
            'activation_map': dict(activation_map),
            'active_interface_groups': sorted(expected_wall_contact_groups_for_stage(stage_name, enabled_ifaces)),
            'active_support_groups': sorted(expected_support_groups_for_stage(stage_name, enabled_supports)) if coupled_mode else [],
        }
        if stage_name == 'initial':
            meta.setdefault('notes', '初始阶段默认仅保留墙体与冠梁，分层支撑按开挖阶段逐步激活。为保证示例在缺少 SciPy sparse 时仍可求解，自动冠梁默认采用 truss2 求解兼容形式。')
        return meta

    return [
        AnalysisStage(name='initial', steps=initial_steps, metadata=_stage_meta('initial', stage_maps.initial)),
        AnalysisStage(name='excavate_level_1', steps=excavation_steps, metadata=_stage_meta('excavate_level_1', stage_maps.excavate_level_1)),
        AnalysisStage(name='excavate_level_2', steps=excavation_steps, metadata=_stage_meta('excavate_level_2', stage_maps.excavate_level_2)),
    ]
