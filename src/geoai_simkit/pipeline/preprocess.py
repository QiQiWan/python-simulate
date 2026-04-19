from __future__ import annotations

from typing import Any

import numpy as np

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, InterfaceDefinition, LoadDefinition, SimulationModel
from geoai_simkit.pipeline.selectors import collect_region_point_ids, resolve_region_selector, union_region_names
from geoai_simkit.pipeline.specs import BoundaryConditionSpec, ExcavationStepSpec, LoadSpec, StageSpec


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


def _coord_key(point: np.ndarray, *, scale: float) -> tuple[int, int, int]:
    return tuple(int(v) for v in np.round(np.asarray(point, dtype=float) / max(scale, 1.0e-9)))


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
    return max(1.0e-6, float(min(spacings))) if spacings else 1.0





def _axis_for_target(target: str) -> tuple[int, str] | None:
    norm = str(target or '').strip().lower()
    mapping = {
        'xmin': (0, 'min'), 'xmax': (0, 'max'),
        'ymin': (1, 'min'), 'ymax': (1, 'max'),
        'zmin': (2, 'min'), 'zmax': (2, 'max'),
    }
    return mapping.get(norm)



def _filter_point_ids_by_target(points: np.ndarray, point_ids: np.ndarray, target: str, tol: float = 1.0e-8) -> np.ndarray:
    norm = str(target or 'all').strip().lower()
    ids = np.asarray(point_ids, dtype=np.int64)
    if ids.size == 0 or norm in {'all', 'point_ids', 'selection', 'region'}:
        return ids
    axis_spec = _axis_for_target(norm)
    if axis_spec is None:
        return ids
    axis, side = axis_spec
    coords = np.asarray(points[ids, axis], dtype=float)
    anchor = float(np.min(coords) if side == 'min' else np.max(coords))
    mask = np.isclose(coords, anchor, atol=tol)
    return np.asarray(ids[mask], dtype=np.int64)



def resolve_boundary_condition_spec(model: SimulationModel, bc: BoundaryCondition | BoundaryConditionSpec) -> BoundaryCondition:
    if isinstance(bc, BoundaryCondition):
        return bc
    region_names = union_region_names(model, explicit_names=tuple(bc.region_names), selector=bc.selector)
    if not region_names:
        return BoundaryCondition(name=bc.name, kind=bc.kind, target=bc.target, components=tuple(int(v) for v in bc.components), values=tuple(float(v) for v in bc.values), metadata=dict(bc.metadata or {}))
    point_ids = collect_region_point_ids(model, region_names)
    points = np.asarray(model.to_unstructured_grid().points, dtype=float)
    resolved_ids = _filter_point_ids_by_target(points, point_ids, bc.target)
    metadata = dict(bc.metadata or {})
    metadata.update({'point_ids': tuple(int(v) for v in resolved_ids.tolist()), 'point_id_space': 'global', 'resolved_regions': list(region_names), 'original_target': str(bc.target), 'resolved_by': 'pipeline.boundary_selector'})
    return BoundaryCondition(name=bc.name, kind=bc.kind, target='point_ids', components=tuple(int(v) for v in bc.components), values=tuple(float(v) for v in bc.values), metadata=metadata)



def resolve_load_spec(model: SimulationModel, load: LoadDefinition | LoadSpec) -> LoadDefinition:
    if isinstance(load, LoadDefinition):
        return load
    region_names = union_region_names(model, explicit_names=tuple(load.region_names), selector=load.selector)
    if not region_names:
        return LoadDefinition(name=load.name, kind=load.kind, target=load.target, values=tuple(float(v) for v in load.values), metadata=dict(load.metadata or {}))
    point_ids = collect_region_point_ids(model, region_names)
    points = np.asarray(model.to_unstructured_grid().points, dtype=float)
    resolved_ids = _filter_point_ids_by_target(points, point_ids, load.target)
    metadata = dict(load.metadata or {})
    metadata.update({'point_ids': tuple(int(v) for v in resolved_ids.tolist()), 'point_id_space': 'global', 'resolved_regions': list(region_names), 'original_target': str(load.target), 'resolved_by': 'pipeline.load_selector'})
    return LoadDefinition(name=load.name, kind=load.kind, target='point_ids', values=tuple(float(v) for v in load.values), metadata=metadata)


def resolve_stage_spec(model: SimulationModel, spec: StageSpec) -> AnalysisStage:
    activate_regions = tuple(dict.fromkeys([*spec.activate_regions, *resolve_region_selector(model, spec.activate_selector)]))
    deactivate_regions = tuple(dict.fromkeys([*spec.deactivate_regions, *resolve_region_selector(model, spec.deactivate_selector)]))
    meta = dict(spec.metadata)
    if spec.activate_selector is not None:
        meta.setdefault('resolved_activate_regions', list(activate_regions))
    if spec.deactivate_selector is not None:
        meta.setdefault('resolved_deactivate_regions', list(deactivate_regions))
    activation_map = dict(spec.activation_map or {}) if spec.activation_map is not None else None
    if activation_map is not None:
        for name in activate_regions:
            activation_map[str(name)] = True
        for name in deactivate_regions:
            activation_map[str(name)] = False
    boundary_conditions = tuple(resolve_boundary_condition_spec(model, item) for item in spec.boundary_conditions)
    loads = tuple(resolve_load_spec(model, item) for item in spec.loads)
    if any(isinstance(item, BoundaryConditionSpec) for item in spec.boundary_conditions):
        meta.setdefault('resolved_boundary_conditions', [item.name for item in boundary_conditions])
    if any(isinstance(item, LoadSpec) for item in spec.loads):
        meta.setdefault('resolved_loads', [item.name for item in loads])
    return AnalysisStage(
        name=spec.name,
        activate_regions=activate_regions,
        deactivate_regions=deactivate_regions,
        boundary_conditions=boundary_conditions,
        loads=loads,
        steps=spec.steps,
        metadata={**meta, **({'activation_map': activation_map} if activation_map is not None else {})},
    )


def resolve_excavation_steps(model: SimulationModel, excavation_steps: tuple[ExcavationStepSpec, ...]) -> tuple[ExcavationStepSpec, ...]:
    resolved: list[ExcavationStepSpec] = []
    for step in excavation_steps:
        activate_regions = tuple(dict.fromkeys([*step.activate_regions, *resolve_region_selector(model, step.activate_selector)]))
        deactivate_regions = tuple(dict.fromkeys([*step.deactivate_regions, *resolve_region_selector(model, step.deactivate_selector)]))
        meta = dict(step.metadata)
        if step.activate_selector is not None:
            meta.setdefault('resolved_activate_regions', list(activate_regions))
        if step.deactivate_selector is not None:
            meta.setdefault('resolved_deactivate_regions', list(deactivate_regions))
        resolved.append(ExcavationStepSpec(name=str(step.name), deactivate_regions=deactivate_regions, activate_regions=activate_regions, steps=step.steps, metadata=meta))
    return tuple(resolved)


def build_node_pair_contact(model: SimulationModel, *, slave_region: str, master_region: str, active_stages: tuple[str, ...] = (), parameters: dict[str, Any] | None = None, name: str | None = None, search_radius_factor: float = 1.75, exact_only: bool = False, avoid_identical_pairs: bool = False, metadata: dict[str, Any] | None = None, slave_point_subset: tuple[int, ...] | list[int] | np.ndarray | None = None, master_point_subset: tuple[int, ...] | list[int] | np.ndarray | None = None) -> InterfaceDefinition | None:
    grid = model.to_unstructured_grid()
    points = np.asarray(grid.points, dtype=float)
    region_points = _region_point_ids(model)
    slave_ids = np.asarray(region_points.get(slave_region, np.empty((0,), dtype=np.int64)), dtype=np.int64)
    master_ids = np.asarray(region_points.get(master_region, np.empty((0,), dtype=np.int64)), dtype=np.int64)
    if slave_point_subset is not None:
        subset = np.asarray(tuple(int(v) for v in slave_point_subset), dtype=np.int64)
        slave_ids = np.intersect1d(slave_ids, subset, assume_unique=False)
    if master_point_subset is not None:
        subset = np.asarray(tuple(int(v) for v in master_point_subset), dtype=np.int64)
        master_ids = np.intersect1d(master_ids, subset, assume_unique=False)
    if slave_ids.size == 0 or master_ids.size == 0:
        return None
    reference_spacing = min(_estimate_reference_spacing(points, slave_ids), _estimate_reference_spacing(points, master_ids))
    scale = max(1.0e-7, reference_spacing * 0.25)
    exact_radius = max(scale * 0.6, 1.0e-8)
    nearest_radius = max(reference_spacing * max(1.0, float(search_radius_factor)), exact_radius * 10.0)
    master_map: dict[tuple[int, int, int], list[int]] = {}
    for pid in master_ids:
        master_map.setdefault(_coord_key(points[int(pid)], scale=scale), []).append(int(pid))
    paired_slave: list[int] = []
    paired_master: list[int] = []
    exact_matches = 0
    nearest_matches = 0
    unmatched = 0
    identical_skipped = 0
    max_pair_distance = 0.0
    used_pairs: set[tuple[int, int]] = set()
    for slave_pid in slave_ids:
        target = np.asarray(points[int(slave_pid)], dtype=float)
        chosen_master: int | None = None
        key = _coord_key(target, scale=scale)
        for candidate in master_map.get(key, []):
            if avoid_identical_pairs and int(candidate) == int(slave_pid):
                identical_skipped += 1
                continue
            dist = float(np.linalg.norm(np.asarray(points[int(candidate)], dtype=float) - target))
            if dist <= exact_radius:
                chosen_master = int(candidate)
                exact_matches += 1
                max_pair_distance = max(max_pair_distance, dist)
                break
        if chosen_master is None and not exact_only:
            best_dist = float('inf')
            for candidate in master_ids:
                if avoid_identical_pairs and int(candidate) == int(slave_pid):
                    identical_skipped += 1
                    continue
                dist = float(np.linalg.norm(np.asarray(points[int(candidate)], dtype=float) - target))
                if dist < best_dist:
                    best_dist = dist
                    chosen_master = int(candidate)
            if chosen_master is None or best_dist > nearest_radius:
                chosen_master = None
            else:
                nearest_matches += 1
                max_pair_distance = max(max_pair_distance, float(best_dist))
        if chosen_master is None:
            unmatched += 1
            continue
        pair = (int(slave_pid), int(chosen_master))
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        paired_slave.append(pair[0])
        paired_master.append(pair[1])
    if not paired_slave:
        return None
    meta = dict(metadata or {})
    meta.update({'source': 'generic_mesh_preparation', 'slave_region': slave_region, 'master_region': master_region, 'pair_count': len(paired_slave), 'exact_match_count': exact_matches, 'nearest_match_count': nearest_matches, 'unmatched_slave_points': unmatched, 'identical_pair_candidates_skipped': int(identical_skipped), 'avoid_identical_pairs': bool(avoid_identical_pairs), 'max_pair_distance': float(max_pair_distance), 'slave_subset_size': int(slave_ids.size), 'master_subset_size': int(master_ids.size)})
    pars = {'kn': 5.0e8, 'ks': 1.0e8, 'friction_deg': 25.0}
    pars.update(dict(parameters or {}))
    return InterfaceDefinition(name=name or f'{slave_region}__to__{master_region}', kind='node_pair', slave_point_ids=tuple(int(v) for v in paired_slave), master_point_ids=tuple(int(v) for v in paired_master), parameters=pars, active_stages=tuple(active_stages), metadata=meta)


def build_stage_sequence_from_excavation(model: SimulationModel, excavation_steps: tuple[Any, ...], *, initial_stage_name: str = 'initial', initial_metadata: dict[str, Any] | None = None) -> list[AnalysisStage]:
    activation_map = {region.name: True for region in model.region_tags}
    stages: list[AnalysisStage] = [AnalysisStage(name=initial_stage_name, metadata={'activation_map': dict(activation_map), **dict(initial_metadata or {})})]
    for step in resolve_excavation_steps(model, tuple(excavation_steps)):
        for name in getattr(step, 'activate_regions', ()):
            if str(name):
                activation_map[str(name)] = True
        for name in getattr(step, 'deactivate_regions', ()):
            if str(name):
                activation_map[str(name)] = False
        stages.append(AnalysisStage(name=str(step.name), activate_regions=tuple(str(v) for v in getattr(step, 'activate_regions', ())), deactivate_regions=tuple(str(v) for v in getattr(step, 'deactivate_regions', ())), steps=getattr(step, 'steps', None), metadata={'activation_map': dict(activation_map), **dict(getattr(step, 'metadata', {}) or {})}))
    return stages
