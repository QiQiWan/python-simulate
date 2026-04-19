from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import BoundaryCondition, InterfaceDefinition, LoadDefinition, SimulationModel, StructuralElementDefinition
from geoai_simkit.pipeline.topology import InterfaceTopologySnapshot, analyze_interface_topology


@dataclass(slots=True)
class InterfaceReadyReport:
    applied: bool
    duplicate_side: str
    duplicated_point_count: int
    duplicated_region_point_count: int
    updated_interface_count: int
    updated_structure_count: int
    updated_boundary_condition_count: int
    updated_stage_boundary_condition_count: int
    updated_stage_load_count: int
    topology_before: InterfaceTopologySnapshot
    topology_after: InterfaceTopologySnapshot
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'applied': bool(self.applied),
            'duplicate_side': self.duplicate_side,
            'duplicated_point_count': int(self.duplicated_point_count),
            'duplicated_region_point_count': int(self.duplicated_region_point_count),
            'updated_interface_count': int(self.updated_interface_count),
            'updated_structure_count': int(self.updated_structure_count),
            'updated_boundary_condition_count': int(self.updated_boundary_condition_count),
            'updated_stage_boundary_condition_count': int(self.updated_stage_boundary_condition_count),
            'updated_stage_load_count': int(self.updated_stage_load_count),
            'topology_before': self.topology_before.to_dict(),
            'topology_after': self.topology_after.to_dict(),
            'metadata': dict(self.metadata),
        }


def _point_region_owners(model: SimulationModel) -> dict[int, set[str]]:
    grid = model.to_unstructured_grid()
    owners: dict[int, set[str]] = {}
    for region in model.region_tags:
        region_name = str(region.name)
        for cid in getattr(region, 'cell_ids', ()):  # pragma: no branch - tiny loops
            try:
                cell = grid.get_cell(int(cid))
            except Exception:
                continue
            for pid in getattr(cell, 'point_ids', ()):
                owners.setdefault(int(pid), set()).add(region_name)
    return owners


def _region_cell_ids(model: SimulationModel) -> dict[str, tuple[int, ...]]:
    return {str(region.name): tuple(int(v) for v in getattr(region, 'cell_ids', ())) for region in model.region_tags}


def _rebuild_grid_with_point_duplication(
    grid: pv.UnstructuredGrid,
    *,
    region_point_map: dict[str, dict[int, int]],
    region_cell_ids: dict[str, tuple[int, ...]],
) -> pv.UnstructuredGrid:
    points = np.asarray(grid.points, dtype=float)
    if not region_point_map:
        return grid.copy(deep=True)
    n_old_points = int(points.shape[0])
    new_points = points.copy()
    ordered_duplicates: list[tuple[str, int, int]] = []
    for region_name in sorted(region_point_map):
        mapping = region_point_map[region_name]
        for old_pid, new_pid in sorted(mapping.items(), key=lambda item: int(item[1])):
            ordered_duplicates.append((region_name, int(old_pid), int(new_pid)))
            new_points = np.vstack([new_points, points[int(old_pid)].reshape(1, 3)])
    if int(new_points.shape[0]) != n_old_points + len(ordered_duplicates):
        raise RuntimeError('Point duplication bookkeeping mismatch while rebuilding the interface-ready mesh.')

    cell_replacements: dict[int, dict[int, int]] = {}
    for region_name, mapping in region_point_map.items():
        for cid in region_cell_ids.get(region_name, ()):
            local = cell_replacements.setdefault(int(cid), {})
            for old_pid, new_pid in mapping.items():
                local[int(old_pid)] = int(new_pid)

    legacy_cells: list[int] = []
    for cid in range(int(grid.n_cells)):
        cell = grid.get_cell(cid)
        point_ids = [int(v) for v in getattr(cell, 'point_ids', ())]
        if cid in cell_replacements:
            repl = cell_replacements[cid]
            point_ids = [int(repl.get(pid, pid)) for pid in point_ids]
        legacy_cells.extend([len(point_ids), *point_ids])

    new_grid = pv.UnstructuredGrid(np.asarray(legacy_cells, dtype=np.int64), np.asarray(grid.celltypes, dtype=np.uint8), np.asarray(new_points, dtype=float))
    for name in getattr(grid, 'cell_data', {}).keys():
        new_grid.cell_data[name] = np.asarray(grid.cell_data[name]).copy()
    for name in getattr(grid, 'point_data', {}).keys():
        arr = np.asarray(grid.point_data[name])
        if arr.ndim == 1:
            extras = [arr[int(old_pid)] for _, old_pid, _ in ordered_duplicates]
            new_arr = np.concatenate([arr.copy(), np.asarray(extras, dtype=arr.dtype)]) if extras else arr.copy()
        else:
            extras = [np.asarray(arr[int(old_pid)], dtype=arr.dtype).reshape(1, *arr.shape[1:]) for _, old_pid, _ in ordered_duplicates]
            new_arr = np.concatenate([arr.copy(), *extras], axis=0) if extras else arr.copy()
        new_grid.point_data[name] = new_arr
    for name in getattr(grid, 'field_data', {}).keys():
        new_grid.field_data[name] = np.asarray(grid.field_data[name]).copy()
    return new_grid


def _choose_region_duplicate(
    old_pid: int,
    *,
    preferred_regions: tuple[str, ...],
    owners: dict[int, set[str]],
    region_point_map: dict[str, dict[int, int]],
) -> int | None:
    owner_regions = tuple(sorted(owners.get(int(old_pid), set())))
    for region_name in preferred_regions:
        if region_name in owner_regions and int(old_pid) in region_point_map.get(region_name, {}):
            return int(region_point_map[region_name][int(old_pid)])
    candidates = [int(mapping[int(old_pid)]) for region_name, mapping in region_point_map.items() if int(old_pid) in mapping and (not owner_regions or region_name in owner_regions)]
    if len(candidates) == 1:
        return int(candidates[0])
    return None


def _remap_interface(
    item: InterfaceDefinition,
    *,
    plan_lookup: dict[str, tuple[str, ...]],
    duplicate_side: str,
    owners: dict[int, set[str]],
    region_point_map: dict[str, dict[int, int]],
) -> tuple[InterfaceDefinition, bool]:
    source_regions = tuple(plan_lookup.get(str(item.name), ()))
    if not source_regions:
        return item, False
    changed = False
    if duplicate_side == 'slave':
        new_slave: list[int] = []
        for old_pid in item.slave_point_ids:
            repl = _choose_region_duplicate(int(old_pid), preferred_regions=source_regions, owners=owners, region_point_map=region_point_map)
            new_slave.append(int(repl if repl is not None else old_pid))
            changed = changed or repl is not None
        meta = dict(item.metadata or {})
        if changed:
            meta['interface_ready_duplicate_side'] = 'slave'
            meta['interface_ready_source_regions'] = list(source_regions)
            return replace(item, slave_point_ids=tuple(new_slave), metadata=meta), True
        return item, False
    new_master: list[int] = []
    for old_pid in item.master_point_ids:
        repl = _choose_region_duplicate(int(old_pid), preferred_regions=source_regions, owners=owners, region_point_map=region_point_map)
        new_master.append(int(repl if repl is not None else old_pid))
        changed = changed or repl is not None
    meta = dict(item.metadata or {})
    if changed:
        meta['interface_ready_duplicate_side'] = 'master'
        meta['interface_ready_source_regions'] = list(source_regions)
        return replace(item, master_point_ids=tuple(new_master), metadata=meta), True
    return item, False


def _remap_structure_points(
    structures: list[StructuralElementDefinition],
    *,
    owners: dict[int, set[str]],
    region_point_map: dict[str, dict[int, int]],
) -> tuple[list[StructuralElementDefinition], int]:
    out: list[StructuralElementDefinition] = []
    updated = 0
    for item in structures:
        changed = False
        new_point_ids: list[int] = []
        for old_pid in item.point_ids:
            repl = _choose_region_duplicate(int(old_pid), preferred_regions=tuple(sorted(owners.get(int(old_pid), set()))), owners=owners, region_point_map=region_point_map)
            new_point_ids.append(int(repl if repl is not None else old_pid))
            changed = changed or repl is not None
        if changed:
            meta = dict(item.metadata or {})
            meta['interface_ready_remapped'] = True
            out.append(replace(item, point_ids=tuple(new_point_ids), metadata=meta))
            updated += 1
        else:
            out.append(item)
    return out, updated


def _remap_point_metadata(point_ids: tuple[int, ...], *, resolved_regions: tuple[str, ...], owners: dict[int, set[str]], region_point_map: dict[str, dict[int, int]]) -> tuple[tuple[int, ...], bool]:
    changed = False
    out: list[int] = []
    for old_pid in point_ids:
        repl = _choose_region_duplicate(int(old_pid), preferred_regions=resolved_regions, owners=owners, region_point_map=region_point_map)
        out.append(int(repl if repl is not None else old_pid))
        changed = changed or repl is not None
    return tuple(out), changed


def _remap_boundary_condition_metadata(items: list[BoundaryCondition], *, owners: dict[int, set[str]], region_point_map: dict[str, dict[int, int]]) -> tuple[list[BoundaryCondition], int]:
    out: list[BoundaryCondition] = []
    updated = 0
    for item in items:
        meta = dict(item.metadata or {})
        point_ids = tuple(int(v) for v in meta.get('point_ids', ()) or ())
        resolved_regions = tuple(str(v) for v in meta.get('resolved_regions', ()) or ())
        if point_ids and resolved_regions:
            new_ids, changed = _remap_point_metadata(point_ids, resolved_regions=resolved_regions, owners=owners, region_point_map=region_point_map)
            if changed:
                meta['point_ids'] = new_ids
                meta['interface_ready_remapped'] = True
                out.append(replace(item, metadata=meta))
                updated += 1
                continue
        out.append(item)
    return out, updated


def _remap_load_metadata(items: tuple[LoadDefinition, ...], *, owners: dict[int, set[str]], region_point_map: dict[str, dict[int, int]]) -> tuple[tuple[LoadDefinition, ...], int]:
    out: list[LoadDefinition] = []
    updated = 0
    for item in items:
        meta = dict(item.metadata or {})
        point_ids = tuple(int(v) for v in meta.get('point_ids', ()) or ())
        resolved_regions = tuple(str(v) for v in meta.get('resolved_regions', ()) or ())
        if point_ids and resolved_regions:
            new_ids, changed = _remap_point_metadata(point_ids, resolved_regions=resolved_regions, owners=owners, region_point_map=region_point_map)
            if changed:
                meta['point_ids'] = new_ids
                meta['interface_ready_remapped'] = True
                out.append(replace(item, metadata=meta))
                updated += 1
                continue
        out.append(item)
    return tuple(out), updated


def apply_interface_node_split(model: SimulationModel, *, duplicate_side: str = 'slave') -> InterfaceReadyReport:
    duplicate_side_key = str(duplicate_side or 'slave').strip().lower()
    if duplicate_side_key not in {'slave', 'master'}:
        duplicate_side_key = 'slave'
    topology_before = analyze_interface_topology(model, duplicate_side=duplicate_side_key)
    if not topology_before.split_plans:
        report = InterfaceReadyReport(
            applied=False,
            duplicate_side=duplicate_side_key,
            duplicated_point_count=0,
            duplicated_region_point_count=0,
            updated_interface_count=0,
            updated_structure_count=0,
            updated_boundary_condition_count=0,
            updated_stage_boundary_condition_count=0,
            updated_stage_load_count=0,
            topology_before=topology_before,
            topology_after=topology_before,
            metadata={'reason': 'no_split_plans'},
        )
        model.metadata.setdefault('pipeline.interface_ready', report.to_dict())
        return report

    owners_before = _point_region_owners(model)
    region_cell_ids = _region_cell_ids(model)
    duplicate_requests: dict[str, set[int]] = {}
    plan_lookup: dict[str, tuple[str, ...]] = {}
    for plan in topology_before.split_plans:
        source_regions = tuple(str(v) for v in plan.source_region_names)
        if not source_regions:
            continue
        plan_lookup[str(plan.interface_name)] = source_regions
        for region_name in source_regions:
            duplicate_requests.setdefault(region_name, set()).update(int(v) for v in plan.duplicate_point_ids)

    region_point_map: dict[str, dict[int, int]] = {}
    next_pid = int(model.to_unstructured_grid().n_points)
    for region_name in sorted(duplicate_requests):
        mapping: dict[int, int] = {}
        for old_pid in sorted(duplicate_requests[region_name]):
            mapping[int(old_pid)] = int(next_pid)
            next_pid += 1
        region_point_map[region_name] = mapping

    grid = model.to_unstructured_grid()
    model.mesh = _rebuild_grid_with_point_duplication(grid, region_point_map=region_point_map, region_cell_ids=region_cell_ids)

    updated_interfaces: list[InterfaceDefinition] = []
    updated_interface_count = 0
    for item in model.interfaces:
        remapped, changed = _remap_interface(item, plan_lookup=plan_lookup, duplicate_side=duplicate_side_key, owners=owners_before, region_point_map=region_point_map)
        updated_interfaces.append(remapped)
        updated_interface_count += int(changed)
    model.interfaces = updated_interfaces

    remapped_structures, updated_structure_count = _remap_structure_points(model.structures, owners=owners_before, region_point_map=region_point_map)
    model.structures = remapped_structures
    remapped_bcs, updated_bc_count = _remap_boundary_condition_metadata(model.boundary_conditions, owners=owners_before, region_point_map=region_point_map)
    model.boundary_conditions = remapped_bcs

    updated_stage_bc_count = 0
    updated_stage_load_count = 0
    new_stages = []
    for stage in model.stages:
        stage_bcs, stage_bc_count = _remap_boundary_condition_metadata(list(stage.boundary_conditions), owners=owners_before, region_point_map=region_point_map)
        stage_loads, stage_load_count = _remap_load_metadata(stage.loads, owners=owners_before, region_point_map=region_point_map)
        updated_stage_bc_count += int(stage_bc_count)
        updated_stage_load_count += int(stage_load_count)
        new_stages.append(replace(stage, boundary_conditions=tuple(stage_bcs), loads=tuple(stage_loads)))
    model.stages = new_stages

    topology_after = analyze_interface_topology(model, duplicate_side=duplicate_side_key)
    report = InterfaceReadyReport(
        applied=True,
        duplicate_side=duplicate_side_key,
        duplicated_point_count=int(sum(len(item) for item in duplicate_requests.values())),
        duplicated_region_point_count=int(sum(len(item) for item in region_point_map.values())),
        updated_interface_count=int(updated_interface_count),
        updated_structure_count=int(updated_structure_count),
        updated_boundary_condition_count=int(updated_bc_count),
        updated_stage_boundary_condition_count=int(updated_stage_bc_count),
        updated_stage_load_count=int(updated_stage_load_count),
        topology_before=topology_before,
        topology_after=topology_after,
        metadata={
            'duplicated_regions': {key: len(value) for key, value in region_point_map.items()},
            'region_point_map': {key: {str(old): int(new) for old, new in value.items()} for key, value in region_point_map.items()},
            'split_interfaces': [item.interface_name for item in topology_before.split_plans],
            'n_remaining_split_plans': int(len(topology_after.split_plans)),
            'n_points_before': int(grid.n_points),
            'n_points_after': int(model.to_unstructured_grid().n_points),
        },
    )
    model.metadata.setdefault('pipeline.interface_ready', report.to_dict())
    model.metadata['pipeline.interface_ready_applied'] = True
    return report
