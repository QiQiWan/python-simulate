from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np

from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.solver.staging import StageManager
from geoai_simkit.validation_rules import normalize_region_name

from .bundle import CompilationBundle, CompileReport
from .compile_config import CompileConfig, PartitionConfig
from .halo import build_halo_exchange_plans
from .numbering import build_distributed_numbering
from .partition import _estimate_cell_gp_counts, build_partitions
from .schemas import (
    CompiledStagePlan,
    MemoryBudgetEstimate,
    PartitionedRuntimeModel,
    RuntimeModel,
    StageActivationMask,
)


def _extract_cells(grid) -> tuple[np.ndarray, np.ndarray]:
    cells = np.asarray(getattr(grid, 'cells', []), dtype=np.int64).reshape(-1)
    offsets = np.asarray(getattr(grid, 'offset', []), dtype=np.int64).reshape(-1)
    entries: list[np.ndarray] = []
    arity: list[int] = []
    if offsets.size:
        for start in offsets.tolist():
            npts = int(cells[int(start)])
            pts = cells[int(start) + 1: int(start) + 1 + npts]
            entries.append(np.asarray(pts, dtype=np.int32))
            arity.append(npts)
    else:
        cursor = 0
        while cursor < cells.size:
            npts = int(cells[cursor])
            pts = cells[cursor + 1: cursor + 1 + npts]
            entries.append(np.asarray(pts, dtype=np.int32))
            arity.append(npts)
            cursor += npts + 1
    width = max(arity, default=0)
    conn = np.full((len(entries), width), -1, dtype=np.int32)
    for cell_id, pts in enumerate(entries):
        if pts.size:
            conn[cell_id, : pts.size] = pts
    return conn, np.asarray(arity, dtype=np.int16)


def _cell_region_arrays(model: SimulationModel, cell_count: int) -> tuple[np.ndarray, dict[str, int], dict[int, str]]:
    region_codes = np.zeros(cell_count, dtype=np.int16)
    name_to_code: dict[str, int] = {}
    code_to_name: dict[int, str] = {0: '__unassigned__'}
    next_code = 1
    for region in model.region_tags:
        norm = normalize_region_name(region.name)
        if norm not in name_to_code:
            name_to_code[norm] = next_code
            code_to_name[next_code] = str(region.name)
            next_code += 1
        region_codes[np.asarray(region.cell_ids, dtype=np.int64)] = name_to_code[norm]
    return region_codes, name_to_code, code_to_name


def _material_codes(model: SimulationModel, region_codes: np.ndarray, code_to_name: dict[int, str]) -> tuple[np.ndarray, dict[int, str]]:
    material_codes = np.zeros(region_codes.shape[0], dtype=np.int16)
    material_name_to_code: dict[str, int] = {'__unassigned__': 0}
    code_to_material: dict[int, str] = {0: '__unassigned__'}
    next_code = 1
    for code, region_name in code_to_name.items():
        if int(code) == 0:
            continue
        material = model.material_for_region(region_name)
        if material is None:
            continue
        key = str(material.material_name)
        if key not in material_name_to_code:
            material_name_to_code[key] = next_code
            code_to_material[next_code] = key
            next_code += 1
        material_codes[region_codes == int(code)] = material_name_to_code[key]
    return material_codes, code_to_material


def _compile_stage_plan(model: SimulationModel, runtime_model: RuntimeModel, region_name_to_code: dict[str, int]) -> CompiledStagePlan:
    stage_contexts = StageManager(model).iter_stages()
    if not stage_contexts:
        stage_contexts = [AnalysisStage(name='default')]
    stage_names: list[str] = []
    topo_order: list[int] = []
    predecessor_index: list[int] = []
    activation_masks: list[StageActivationMask] = []
    bc_tables: list[Any] = []
    load_tables: list[Any] = []
    structure_masks: list[np.ndarray] = []
    interface_masks: list[np.ndarray] = []
    stage_index_by_name: dict[str, int] = {}
    for stage_index, stage_ctx in enumerate(stage_contexts):
        stage = stage_ctx.stage
        stage_names.append(stage.name)
        topo_order.append(stage_index)
        pred_name = str((stage.metadata or {}).get('predecessor') or '').strip()
        predecessor_index.append(stage_index_by_name.get(pred_name, -1))
        stage_index_by_name[stage.name] = stage_index
        active_region_codes = np.asarray(
            sorted(
                {
                    int(region_name_to_code[normalize_region_name(name)])
                    for name in stage_ctx.active_regions
                    if normalize_region_name(name) in region_name_to_code
                }
            ),
            dtype=np.int16,
        )
        active_cell_mask = np.isin(np.asarray(runtime_model.region_codes, dtype=np.int16), active_region_codes)
        structure_mask = np.asarray(
            [not item.active_stages or stage.name in item.active_stages for item in model.structures],
            dtype=np.uint8,
        )
        interface_mask = np.asarray(
            [not item.active_stages or stage.name in item.active_stages for item in model.interfaces],
            dtype=np.uint8,
        )
        activation_masks.append(
            StageActivationMask(
                active_region_codes=active_region_codes,
                active_cell_mask=active_cell_mask,
                active_structure_mask=structure_mask,
                active_interface_mask=interface_mask,
                metadata={'active_region_names': sorted(stage_ctx.active_regions)},
            )
        )
        bc_tables.append(tuple(model.boundary_conditions) + tuple(stage.boundary_conditions))
        load_tables.append(tuple(stage.loads))
        structure_masks.append(structure_mask)
        interface_masks.append(interface_mask)
    return CompiledStagePlan(
        stage_names=tuple(stage_names),
        topo_order=tuple(topo_order),
        predecessor_index=tuple(predecessor_index),
        activation_masks=tuple(activation_masks),
        bc_tables=tuple(bc_tables),
        load_tables=tuple(load_tables),
        structure_masks=tuple(structure_masks),
        interface_masks=tuple(interface_masks),
        metadata={'stage_count': len(stage_names)},
    )


def _estimate_memory(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
) -> MemoryBudgetEstimate:
    geometry_bytes = int(
        np.asarray(runtime_model.node_coords).nbytes
        + np.asarray(runtime_model.cell_conn).nbytes
        + np.asarray(runtime_model.cell_type_codes).nbytes
        + np.asarray(runtime_model.region_codes).nbytes
        + np.asarray(runtime_model.material_codes).nbytes
    )
    node_count = int(runtime_model.node_count)
    dof_per_node = int(runtime_model.dof_per_node)
    cell_count = int(runtime_model.cell_count)
    field_bytes = int(node_count * dof_per_node * 8 * 6)
    gp_state_bytes = int(cell_count * 8 * 6 * 8 * 3)
    linear_system_bytes = int(max(1, node_count * dof_per_node) * 64)
    halo_bytes = int(
        sum(int(plan.metadata.get('halo_dof_count', 0)) for plan in partitioned_model.halo_plans) * 8
    )
    checkpoint_peak_bytes = int(field_bytes + gp_state_bytes)
    total_peak_bytes = int(
        geometry_bytes + field_bytes + gp_state_bytes + linear_system_bytes + halo_bytes + checkpoint_peak_bytes
    )
    return MemoryBudgetEstimate(
        geometry_bytes=geometry_bytes,
        field_bytes=field_bytes,
        gp_state_bytes=gp_state_bytes,
        linear_system_bytes=linear_system_bytes,
        halo_bytes=halo_bytes,
        checkpoint_peak_bytes=checkpoint_peak_bytes,
        total_peak_bytes=total_peak_bytes,
    )


def _verify_partitioned_model(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
) -> dict[str, object]:
    partitions = tuple(partitioned_model.partitions)
    halo_plans = tuple(partitioned_model.halo_plans)
    numbering = partitioned_model.numbering
    issues: list[str] = []

    owned_cell_ids = (
        np.concatenate([np.asarray(part.owned_cell_ids, dtype=np.int64) for part in partitions]).astype(np.int64, copy=False)
        if partitions
        else np.asarray([], dtype=np.int64)
    )
    unique_owned_cells = np.unique(owned_cell_ids) if owned_cell_ids.size else np.asarray([], dtype=np.int64)
    if int(unique_owned_cells.size) != int(runtime_model.cell_count):
        issues.append(
            f'owned cell coverage mismatch: covered={int(unique_owned_cells.size)} expected={int(runtime_model.cell_count)}'
        )
    if owned_cell_ids.size != unique_owned_cells.size:
        issues.append('owned cell ids are duplicated across partitions')

    connected_nodes = np.unique(
        np.asarray(runtime_model.cell_conn, dtype=np.int64)[np.asarray(runtime_model.cell_conn, dtype=np.int64) >= 0]
    ) if int(runtime_model.cell_count) else np.asarray([], dtype=np.int64)
    owned_node_ids = (
        np.concatenate([np.asarray(part.owned_node_ids, dtype=np.int64) for part in partitions]).astype(np.int64, copy=False)
        if partitions
        else np.asarray([], dtype=np.int64)
    )
    unique_owned_nodes = np.unique(owned_node_ids) if owned_node_ids.size else np.asarray([], dtype=np.int64)
    if owned_node_ids.size != unique_owned_nodes.size:
        issues.append('owned node ids are duplicated across partitions')
    if connected_nodes.size and unique_owned_nodes.size != connected_nodes.size:
        issues.append(
            f'owned node coverage mismatch: covered={int(unique_owned_nodes.size)} expected_connected={int(connected_nodes.size)}'
        )

    halo_pair_map = {int(plan.partition_id): plan for plan in halo_plans}
    for partition in partitions:
        for neighbor in partition.neighbor_partition_ids:
            if int(neighbor) not in halo_pair_map:
                issues.append(f'partition {partition.partition_id} references missing halo plan for neighbor {neighbor}')
                continue
            other = next((item for item in partitions if int(item.partition_id) == int(neighbor)), None)
            if other is None or int(partition.partition_id) not in {int(item) for item in other.neighbor_partition_ids}:
                issues.append(
                    f'neighbor relation is not reciprocal between partitions {partition.partition_id} and {neighbor}'
                )

    halo_reciprocity_ok = True
    for plan in halo_plans:
        for neighbor, recv_nodes in zip(plan.recv_neighbors, plan.recv_node_ids):
            neighbor_plan = halo_pair_map.get(int(neighbor))
            if neighbor_plan is None:
                halo_reciprocity_ok = False
                issues.append(f'halo plan missing for neighbor partition {neighbor}')
                continue
            neighbor_send_nodes = None
            for send_neighbor, send_nodes in zip(neighbor_plan.send_neighbors, neighbor_plan.send_node_ids):
                if int(send_neighbor) == int(plan.partition_id):
                    neighbor_send_nodes = np.asarray(send_nodes, dtype=np.int64)
                    break
            recv_nodes_arr = np.asarray(recv_nodes, dtype=np.int64)
            if neighbor_send_nodes is None or not np.array_equal(
                np.asarray(np.sort(recv_nodes_arr), dtype=np.int64),
                np.asarray(np.sort(neighbor_send_nodes), dtype=np.int64),
            ):
                halo_reciprocity_ok = False
                issues.append(
                    f'halo reciprocity mismatch between partitions {plan.partition_id} and {neighbor}'
                )

    invalid_dof_partitions = []
    for index, partition in enumerate(partitions):
        owned_dofs = np.asarray(numbering.owned_dof_ids[index], dtype=np.int64)
        ghost_dofs = np.asarray(numbering.ghost_dof_ids[index], dtype=np.int64)
        if owned_dofs.size and np.any(owned_dofs < 0):
            invalid_dof_partitions.append(int(partition.partition_id))
        if ghost_dofs.size and np.any(ghost_dofs < 0):
            invalid_dof_partitions.append(int(partition.partition_id))
        if np.intersect1d(owned_dofs, ghost_dofs).size:
            issues.append(f'owned/ghost dof overlap detected in partition {partition.partition_id}')
    if invalid_dof_partitions:
        issues.append(f'invalid dof ids detected in partitions {sorted(set(invalid_dof_partitions))}')

    partition_summaries = [
        {
            'partition_id': int(part.partition_id),
            'owned_cell_count': int(np.asarray(part.owned_cell_ids).size),
            'owned_node_count': int(np.asarray(part.owned_node_ids).size),
            'ghost_node_count': int(np.asarray(part.ghost_node_ids).size),
            'neighbor_count': len(part.neighbor_partition_ids),
            'neighbors': [int(item) for item in part.neighbor_partition_ids],
            'owned_dof_count': int(part.metadata.get('owned_dof_count', 0) or 0),
            'gp_state_count': int(part.metadata.get('gp_state_count', 0) or 0),
            'halo_node_count': (
                0
                if int(part.partition_id) not in halo_pair_map
                else int(halo_pair_map[int(part.partition_id)].metadata.get('halo_node_count', 0) or 0)
            ),
            'halo_dof_count': (
                0
                if int(part.partition_id) not in halo_pair_map
                else int(halo_pair_map[int(part.partition_id)].metadata.get('halo_dof_count', 0) or 0)
            ),
        }
        for part in partitions
    ]

    return {
        'ok': not issues,
        'issues': issues,
        'halo_reciprocity_ok': bool(halo_reciprocity_ok),
        'owned_cell_total': int(owned_cell_ids.size),
        'unique_owned_cell_total': int(unique_owned_cells.size),
        'owned_node_total': int(owned_node_ids.size),
        'unique_owned_node_total': int(unique_owned_nodes.size),
        'connected_node_total': int(connected_nodes.size),
        'partition_summaries': partition_summaries,
    }


def _stage_partition_diagnostics(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
) -> list[dict[str, object]]:
    partitions = tuple(partitioned_model.partitions)
    if not partitions:
        return []
    gp_counts_by_cell = _estimate_cell_gp_counts(runtime_model)
    cell_conn = np.asarray(runtime_model.cell_conn, dtype=np.int64)
    dof_per_node = max(1, int(runtime_model.dof_per_node))
    diagnostics: list[dict[str, object]] = []
    stage_plan = runtime_model.stage_plan
    total_cell_count = max(1, int(runtime_model.cell_count))
    total_node_count = max(1, int(runtime_model.node_count))
    for stage_index, stage_name in enumerate(stage_plan.stage_names):
        activation_mask = stage_plan.activation_masks[stage_index]
        active_cell_mask = np.asarray(activation_mask.active_cell_mask, dtype=bool).reshape(-1)
        active_cells_per_partition: list[int] = []
        active_gp_states_per_partition: list[int] = []
        active_owned_nodes_per_partition: list[int] = []
        active_local_nodes_per_partition: list[int] = []
        active_owned_dofs_per_partition: list[int] = []
        active_local_dofs_per_partition: list[int] = []
        idle_partition_ids: list[int] = []
        for partition in partitions:
            owned_cell_ids = np.asarray(partition.owned_cell_ids, dtype=np.int64).reshape(-1)
            if owned_cell_ids.size:
                owned_active_mask = active_cell_mask[owned_cell_ids]
                active_owned_cell_ids = owned_cell_ids[owned_active_mask]
                active_cell_count = int(np.count_nonzero(owned_active_mask))
                active_gp_count = int(np.asarray(gp_counts_by_cell[owned_cell_ids], dtype=np.int32)[owned_active_mask].sum())
                if active_owned_cell_ids.size:
                    active_local_node_ids = np.unique(
                        np.asarray(cell_conn[active_owned_cell_ids], dtype=np.int64)[
                            np.asarray(cell_conn[active_owned_cell_ids], dtype=np.int64) >= 0
                        ]
                    )
                    owned_node_ids = np.asarray(partition.owned_node_ids, dtype=np.int64).reshape(-1)
                    active_owned_node_count = int(
                        np.intersect1d(active_local_node_ids, owned_node_ids, assume_unique=False).size
                    )
                    active_local_node_count = int(active_local_node_ids.size)
                else:
                    active_owned_node_count = 0
                    active_local_node_count = 0
            else:
                active_cell_count = 0
                active_gp_count = 0
                active_owned_node_count = 0
                active_local_node_count = 0
            active_cells_per_partition.append(active_cell_count)
            active_gp_states_per_partition.append(active_gp_count)
            active_owned_nodes_per_partition.append(active_owned_node_count)
            active_local_nodes_per_partition.append(active_local_node_count)
            active_owned_dofs_per_partition.append(int(active_owned_node_count * dof_per_node))
            active_local_dofs_per_partition.append(int(active_local_node_count * dof_per_node))
            if active_cell_count <= 0:
                idle_partition_ids.append(int(partition.partition_id))
        active_partition_counts = [count for count in active_cells_per_partition if count > 0]
        active_owned_node_counts = [count for count in active_owned_nodes_per_partition if count > 0]
        active_local_node_total = int(sum(active_local_nodes_per_partition))
        diagnostics.append(
            {
                'stage_index': int(stage_index),
                'stage_name': str(stage_name),
                'active_region_names': list(activation_mask.metadata.get('active_region_names', []) or []),
                'active_cell_count': int(np.count_nonzero(active_cell_mask)),
                'active_cell_ratio': float(np.count_nonzero(active_cell_mask) / total_cell_count),
                'active_owned_node_total': int(sum(active_owned_nodes_per_partition)),
                'active_local_node_total': active_local_node_total,
                'active_node_ratio': float(active_local_node_total / total_node_count),
                'active_structure_count': int(np.count_nonzero(np.asarray(stage_plan.structure_masks[stage_index], dtype=np.uint8))),
                'active_interface_count': int(np.count_nonzero(np.asarray(stage_plan.interface_masks[stage_index], dtype=np.uint8))),
                'active_partition_count': int(len(active_partition_counts)),
                'idle_partition_ids': idle_partition_ids,
                'active_cells_per_partition': active_cells_per_partition,
                'active_gp_states_per_partition': active_gp_states_per_partition,
                'active_owned_nodes_per_partition': active_owned_nodes_per_partition,
                'active_local_nodes_per_partition': active_local_nodes_per_partition,
                'active_owned_dofs_per_partition': active_owned_dofs_per_partition,
                'active_local_dofs_per_partition': active_local_dofs_per_partition,
                'active_partition_balance_ratio': (
                    1.0
                    if not active_partition_counts
                    else float(max(active_partition_counts) / max(1, min(active_partition_counts)))
                ),
                'active_node_balance_ratio': (
                    1.0
                    if not active_owned_node_counts
                    else float(max(active_owned_node_counts) / max(1, min(active_owned_node_counts)))
                ),
                'stage_locality_ratio': float(len(active_partition_counts) / max(1, len(partitions))),
            }
        )
    return diagnostics


def _partition_advisory(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
    stage_partition_diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    partition_count = max(1, int(len(partitioned_model.partitions)))
    if not stage_partition_diagnostics:
        return {
            'current_partition_count': partition_count,
            'recommended_partition_count': partition_count,
            'recommended_partition_upper_bound': partition_count,
            'overpartitioned': False,
            'underpartitioned': False,
            'average_active_partition_count': float(partition_count),
            'weighted_active_partition_count': float(partition_count),
            'average_stage_locality_ratio': 1.0,
            'average_idle_partition_count': 0.0,
            'max_idle_partition_count': 0,
            'idle_stage_names': [],
            'reasons': ['No stage diagnostics were available; keeping the current partition count.'],
        }

    active_partition_counts = [
        int(item.get('active_partition_count', partition_count) or partition_count)
        for item in stage_partition_diagnostics
    ]
    stage_weights = [
        max(1.0e-6, float(item.get('active_cell_ratio', 0.0) or 0.0))
        for item in stage_partition_diagnostics
    ]
    locality_ratios = [
        float(item.get('stage_locality_ratio', 1.0) or 1.0)
        for item in stage_partition_diagnostics
    ]
    idle_counts = [
        max(0, partition_count - int(item.get('active_partition_count', partition_count) or partition_count))
        for item in stage_partition_diagnostics
    ]
    total_weight = float(sum(stage_weights)) or 1.0
    weighted_active_partition_count = float(
        sum(float(count) * weight for count, weight in zip(active_partition_counts, stage_weights)) / total_weight
    )
    average_active_partition_count = float(sum(active_partition_counts) / max(1, len(active_partition_counts)))
    average_stage_locality_ratio = float(sum(locality_ratios) / max(1, len(locality_ratios)))
    average_idle_partition_count = float(sum(idle_counts) / max(1, len(idle_counts)))
    max_idle_partition_count = int(max(idle_counts, default=0))
    recommended_partition_count = max(
        1,
        min(
            partition_count,
            int(round(weighted_active_partition_count)),
        ),
    )
    recommended_partition_upper_bound = max(
        1,
        min(partition_count, max(active_partition_counts, default=partition_count)),
    )
    idle_stage_names = [
        str(item.get('stage_name', f'stage-{index}'))
        for index, item in enumerate(stage_partition_diagnostics)
        if int(item.get('active_partition_count', partition_count) or partition_count) < partition_count
    ]
    overpartitioned = bool(
        partition_count > 1
        and (
            recommended_partition_count < partition_count
            or average_stage_locality_ratio < 0.75
            or average_idle_partition_count >= 1.0
        )
    )
    underpartitioned = bool(
        partition_count == 1
        and runtime_model.cell_count >= 128
    )
    reasons: list[str] = []
    if overpartitioned:
        reasons.append(
            'Several stages leave partitions idle under the current partition count; a lower partition count may improve locality.'
        )
    if average_stage_locality_ratio < 0.75:
        reasons.append('Average stage locality is below 0.75, indicating uneven stage activity across partitions.')
    if max_idle_partition_count > 0:
        reasons.append(f'At least one stage leaves {max_idle_partition_count} partitions idle.')
    if underpartitioned:
        reasons.append('Single-partition execution is likely conservative for this mesh size; higher partition counts may be worth comparing.')
    if not reasons:
        reasons.append('Current partition count is within the useful activity envelope observed across stages.')
    return {
        'current_partition_count': partition_count,
        'recommended_partition_count': int(recommended_partition_count),
        'recommended_partition_upper_bound': int(recommended_partition_upper_bound),
        'overpartitioned': bool(overpartitioned),
        'underpartitioned': bool(underpartitioned),
        'average_active_partition_count': float(average_active_partition_count),
        'weighted_active_partition_count': float(weighted_active_partition_count),
        'average_stage_locality_ratio': float(average_stage_locality_ratio),
        'average_idle_partition_count': float(average_idle_partition_count),
        'max_idle_partition_count': int(max_idle_partition_count),
        'idle_stage_names': idle_stage_names,
        'reasons': reasons,
    }


def _estimate_partition_linear_systems(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
) -> list[dict[str, object]]:
    partitions = tuple(partitioned_model.partitions)
    numbering = partitioned_model.numbering
    dof_per_node = max(1, int(runtime_model.dof_per_node))
    estimates: list[dict[str, object]] = []
    for index, partition in enumerate(partitions):
        local_conn = np.asarray(partition.local_cell_conn, dtype=np.int64)
        local_node_ids = (
            np.unique(local_conn[local_conn >= 0]).astype(np.int64, copy=False)
            if local_conn.size
            else np.asarray([], dtype=np.int64)
        )
        block_pairs: set[tuple[int, int]] = set()
        for cell_nodes in local_conn.tolist():
            valid_nodes = [int(node_id) for node_id in cell_nodes if int(node_id) >= 0]
            for row_node in valid_nodes:
                for col_node in valid_nodes:
                    block_pairs.add((row_node, col_node))
        local_node_count = int(local_node_ids.size)
        owned_dof_count = int(np.asarray(numbering.owned_dof_ids[index], dtype=np.int64).size)
        ghost_dof_count = int(np.asarray(numbering.ghost_dof_ids[index], dtype=np.int64).size)
        local_dof_count = int(local_node_count * dof_per_node)
        nnz_blocks = int(len(block_pairs))
        nnz_entries = int(nnz_blocks * dof_per_node * dof_per_node)
        storage_bytes = int(
            nnz_entries * 8
            + max(0, nnz_blocks) * 2 * 8
            + max(0, local_dof_count + 1) * 8
        )
        estimates.append(
            {
                'partition_id': int(partition.partition_id),
                'matrix_shape': [int(local_dof_count), int(local_dof_count)],
                'storage': 'csr-estimate',
                'block_size': int(dof_per_node),
                'owned_cell_count': int(np.asarray(partition.owned_cell_ids, dtype=np.int64).size),
                'owned_node_count': int(np.asarray(partition.owned_node_ids, dtype=np.int64).size),
                'ghost_node_count': int(np.asarray(partition.ghost_node_ids, dtype=np.int64).size),
                'local_node_count': int(local_node_count),
                'owned_dof_count': int(owned_dof_count),
                'ghost_dof_count': int(ghost_dof_count),
                'local_dof_count': int(local_dof_count),
                'matrix_nnz_blocks': int(nnz_blocks),
                'matrix_nnz_entries': int(nnz_entries),
                'matrix_density': (
                    0.0
                    if local_dof_count <= 0
                    else float(nnz_entries / float(local_dof_count * local_dof_count))
                ),
                'matrix_storage_bytes': int(storage_bytes),
            }
        )
    return estimates


def _stage_linear_system_plans(
    runtime_model: RuntimeModel,
    partitioned_model: PartitionedRuntimeModel,
    stage_partition_diagnostics: list[dict[str, object]],
    linear_system_partition_estimates: list[dict[str, object]],
) -> list[dict[str, object]]:
    partitions = tuple(partitioned_model.partitions)
    estimate_by_partition = {
        int(item.get('partition_id', index)): dict(item)
        for index, item in enumerate(linear_system_partition_estimates)
    }
    plans: list[dict[str, object]] = []
    dof_per_node = max(1, int(runtime_model.dof_per_node))
    for stage_index, stage_diag in enumerate(stage_partition_diagnostics):
        active_cells_per_partition = list(stage_diag.get('active_cells_per_partition', []) or [])
        active_gp_states_per_partition = list(stage_diag.get('active_gp_states_per_partition', []) or [])
        active_owned_nodes_per_partition = list(stage_diag.get('active_owned_nodes_per_partition', []) or [])
        active_owned_dofs_per_partition = list(stage_diag.get('active_owned_dofs_per_partition', []) or [])
        partition_local_systems: list[dict[str, object]] = []
        active_partition_ids: list[int] = []
        for partition_index, partition in enumerate(partitions):
            partition_id = int(partition.partition_id)
            estimate_row = dict(estimate_by_partition.get(partition_id, {}))
            owned_cell_count = int(estimate_row.get('owned_cell_count', np.asarray(partition.owned_cell_ids, dtype=np.int64).size) or 0)
            owned_dof_count = int(estimate_row.get('owned_dof_count', int(np.asarray(partition.owned_node_ids, dtype=np.int64).size) * dof_per_node) or 0)
            local_dof_count = int(estimate_row.get('local_dof_count', owned_dof_count) or 0)
            active_cell_count = int(active_cells_per_partition[partition_index]) if partition_index < len(active_cells_per_partition) else 0
            active_gp_state_count = int(active_gp_states_per_partition[partition_index]) if partition_index < len(active_gp_states_per_partition) else 0
            active_owned_node_count = int(active_owned_nodes_per_partition[partition_index]) if partition_index < len(active_owned_nodes_per_partition) else 0
            active_owned_dof_count = int(active_owned_dofs_per_partition[partition_index]) if partition_index < len(active_owned_dofs_per_partition) else 0
            if active_cell_count > 0:
                active_partition_ids.append(partition_id)
            cell_ratio = float(active_cell_count / max(1, owned_cell_count)) if owned_cell_count > 0 else 0.0
            dof_ratio = float(active_owned_dof_count / max(1, owned_dof_count)) if owned_dof_count > 0 else 0.0
            activity_ratio = float(max(0.0, min(1.0, max(cell_ratio, dof_ratio))))
            estimated_local_dof_count = int(round(float(local_dof_count) * activity_ratio))
            estimated_nnz_entries = int(round(float(estimate_row.get('matrix_nnz_entries', 0) or 0) * activity_ratio))
            estimated_nnz_blocks = int(round(float(estimate_row.get('matrix_nnz_blocks', 0) or 0) * activity_ratio))
            estimated_storage_bytes = int(round(float(estimate_row.get('matrix_storage_bytes', 0) or 0) * activity_ratio))
            partition_local_systems.append(
                {
                    'partition_id': partition_id,
                    'active': bool(active_cell_count > 0),
                    'activity_ratio': float(activity_ratio),
                    'active_cell_count': int(active_cell_count),
                    'active_gp_state_count': int(active_gp_state_count),
                    'active_owned_node_count': int(active_owned_node_count),
                    'active_owned_dof_count': int(active_owned_dof_count),
                    'estimated_active_local_dof_count': int(estimated_local_dof_count),
                    'matrix_shape': list(estimate_row.get('matrix_shape', [local_dof_count, local_dof_count]) or [local_dof_count, local_dof_count]),
                    'matrix_nnz_entries_estimate': int(estimated_nnz_entries),
                    'matrix_nnz_blocks_estimate': int(estimated_nnz_blocks),
                    'matrix_storage_bytes_estimate': int(estimated_storage_bytes),
                }
            )
        plans.append(
            {
                'stage_index': int(stage_diag.get('stage_index', stage_index) or stage_index),
                'stage_name': str(stage_diag.get('stage_name', f'stage-{stage_index}')),
                'active_partition_count': int(stage_diag.get('active_partition_count', len(active_partition_ids)) or len(active_partition_ids)),
                'active_partition_ids': active_partition_ids,
                'idle_partition_ids': list(stage_diag.get('idle_partition_ids', []) or []),
                'active_cell_count': int(stage_diag.get('active_cell_count', 0) or 0),
                'active_owned_node_total': int(stage_diag.get('active_owned_node_total', 0) or 0),
                'active_local_node_total': int(stage_diag.get('active_local_node_total', 0) or 0),
                'estimated_active_local_dof_total': int(
                    sum(int(item.get('estimated_active_local_dof_count', 0) or 0) for item in partition_local_systems)
                ),
                'estimated_matrix_storage_bytes': int(
                    sum(int(item.get('matrix_storage_bytes_estimate', 0) or 0) for item in partition_local_systems)
                ),
                'partition_local_systems': partition_local_systems,
            }
        )
    return plans


class RuntimeCompiler:
    def compile_case(self, prepared, config: CompileConfig) -> CompilationBundle:
        started = perf_counter()
        model = prepared.model
        model.ensure_regions()
        grid = model.to_unstructured_grid()
        conn, cell_arity = _extract_cells(grid)
        region_codes, region_name_to_code, code_to_name = _cell_region_arrays(model, int(grid.n_cells))
        material_codes, code_to_material = _material_codes(model, region_codes, code_to_name)
        stage_plan = CompiledStagePlan(
            stage_names=(),
            topo_order=(),
            predecessor_index=(),
            activation_masks=(),
            bc_tables=(),
            load_tables=(),
            structure_masks=(),
            interface_masks=(),
        )
        runtime_model = RuntimeModel(
            name=model.name,
            mesh_kind='unstructured-grid',
            node_count=int(grid.n_points),
            cell_count=int(grid.n_cells),
            spatial_dim=int(np.asarray(grid.points).shape[1]) if int(grid.n_points) else 3,
            dof_per_node=3,
            node_coords=np.asarray(grid.points, dtype=float).copy(),
            cell_conn=conn,
            cell_arity=cell_arity,
            cell_type_codes=np.asarray(getattr(grid, 'celltypes', []), dtype=np.int16),
            region_codes=region_codes,
            material_codes=material_codes,
            bc_table=tuple(model.boundary_conditions),
            load_table=tuple(),
            structure_table=tuple(model.structures),
            interface_table=tuple(model.interfaces),
            stage_plan=stage_plan,
            metadata={
                'region_codebook': {int(code): name for code, name in code_to_name.items()},
                'material_codebook': {int(code): name for code, name in code_to_material.items()},
            },
        )
        runtime_model.stage_plan = _compile_stage_plan(model, runtime_model, region_name_to_code)
        partition_config = PartitionConfig(
            partition_count=config.partition_count,
            strategy=config.partition_strategy,
            metadata=dict(config.metadata),
        )
        partitions, communication_graph = build_partitions(runtime_model, partition_config)
        numbering = build_distributed_numbering(runtime_model, partitions)
        halo_plans = build_halo_exchange_plans(partitions, numbering) if config.enable_halo else ()
        comm_bytes_per_partition = [
            int(
                (
                    sum(np.asarray(dofs, dtype=np.int64).size for dofs in plan.send_dof_ids)
                    + sum(np.asarray(dofs, dtype=np.int64).size for dofs in plan.recv_dof_ids)
                )
                * 8
            )
            for plan in halo_plans
        ]
        partitioned_model = PartitionedRuntimeModel(
            global_model=runtime_model,
            partitions=partitions,
            numbering=numbering,
            communication_graph=communication_graph,
            halo_plans=tuple(halo_plans),
            stage_plan=runtime_model.stage_plan,
            metadata={
                'partition_count': len(partitions),
                'partition_strategy': config.partition_strategy,
                'enable_halo': bool(config.enable_halo),
            },
        )
        memory_estimate = _estimate_memory(runtime_model, partitioned_model)
        partitioned_model.memory_estimate = memory_estimate
        partition_verification = _verify_partitioned_model(runtime_model, partitioned_model)
        stage_partition_diagnostics = _stage_partition_diagnostics(runtime_model, partitioned_model)
        partition_advisory = _partition_advisory(runtime_model, partitioned_model, stage_partition_diagnostics)
        linear_system_partition_estimates = _estimate_partition_linear_systems(runtime_model, partitioned_model)
        stage_linear_system_plans = _stage_linear_system_plans(
            runtime_model,
            partitioned_model,
            stage_partition_diagnostics,
            linear_system_partition_estimates,
        )
        runtime_model.stage_plan.metadata['stage_partition_diagnostics'] = stage_partition_diagnostics
        runtime_model.stage_plan.metadata['stage_linear_system_plans'] = stage_linear_system_plans
        partitioned_model.metadata['linear_system_partition_estimates'] = linear_system_partition_estimates
        partitioned_model.metadata['stage_linear_system_plans'] = stage_linear_system_plans
        runtime_model.metadata['linear_system_partition_estimates'] = linear_system_partition_estimates
        runtime_model.metadata['stage_linear_system_plans'] = stage_linear_system_plans

        warnings: list[str] = []
        errors: list[str] = []
        if not model.materials:
            warnings.append('No material bindings were found in the prepared engineering model.')
        if config.partition_count > int(grid.n_cells) and int(grid.n_cells) > 0:
            warnings.append('Requested partition count exceeded cell count; the compiler reduced the effective partition count.')
        if bool(partition_advisory.get('overpartitioned', False)):
            warnings.append(
                'Partition advisory: the current partition count appears overpartitioned for several stages; review recommended_partition_count.'
            )
        if config.memory_budget_bytes is not None and memory_estimate.total_peak_bytes > int(config.memory_budget_bytes):
            errors.append('Estimated runtime memory exceeds the requested compile memory budget.')
        compile_seconds = float(perf_counter() - started)
        report = CompileReport(
            ok=not errors,
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata={
                'compile_seconds': compile_seconds,
                'node_count': int(runtime_model.node_count),
                'cell_count': int(runtime_model.cell_count),
                'stage_count': len(runtime_model.stage_plan.stage_names),
                'partition_count': len(partitions),
                'partition_balance_ratio': float(communication_graph.metadata.get('cell_balance_ratio', 1.0)),
                'node_balance_ratio': float(communication_graph.metadata.get('node_balance_ratio', 1.0)),
                'dof_balance_ratio': float(communication_graph.metadata.get('dof_balance_ratio', 1.0)),
                'ghost_node_ratio': float(communication_graph.metadata.get('ghost_node_ratio', 0.0)),
                'halo_node_ratio': float(
                    sum(int(plan.metadata.get('halo_node_count', 0) or 0) for plan in halo_plans)
                    / max(1, sum(int(part.metadata.get('owned_node_count', 0) or 0) for part in partitions))
                ),
                'cells_per_partition': list(communication_graph.metadata.get('cells_per_partition', [])),
                'gp_states_per_partition': list(communication_graph.metadata.get('gp_states_per_partition', [])),
                'owned_nodes_per_partition': list(communication_graph.metadata.get('owned_nodes_per_partition', [])),
                'ghost_nodes_per_partition': list(communication_graph.metadata.get('ghost_nodes_per_partition', [])),
                'owned_dofs_per_partition': list(communication_graph.metadata.get('owned_dofs_per_partition', [])),
                'halo_nodes_per_partition': [
                    int(plan.metadata.get('halo_node_count', 0))
                    for plan in partitioned_model.halo_plans
                ],
                'comm_bytes_per_partition': list(comm_bytes_per_partition),
                'estimated_comm_bytes_per_increment': int(sum(comm_bytes_per_partition)),
                'max_neighbor_count': max(
                    (
                        len(part.neighbor_partition_ids)
                        for part in partitions
                    ),
                    default=0,
                ),
                'halo_volume_ratio': float(
                    memory_estimate.halo_bytes / max(1, memory_estimate.total_peak_bytes)
                ),
                'partition_verify_ok': bool(partition_verification['ok']),
                'partition_verify_issues': list(partition_verification['issues']),
                'halo_reciprocity_ok': bool(partition_verification['halo_reciprocity_ok']),
                'owned_cell_total': int(partition_verification['owned_cell_total']),
                'unique_owned_cell_total': int(partition_verification['unique_owned_cell_total']),
                'owned_node_total': int(partition_verification['owned_node_total']),
                'unique_owned_node_total': int(partition_verification['unique_owned_node_total']),
                'connected_node_total': int(partition_verification['connected_node_total']),
                'partition_summaries': list(partition_verification['partition_summaries']),
                'stage_partition_diagnostics': list(stage_partition_diagnostics),
                'stage_linear_system_plans': list(stage_linear_system_plans),
                'partition_advisory': dict(partition_advisory),
                'linear_system_partition_estimates': list(linear_system_partition_estimates),
                'estimated_peak_memory_bytes': int(memory_estimate.total_peak_bytes),
                'element_histogram': {
                    str(int(code)): int(np.count_nonzero(np.asarray(runtime_model.cell_type_codes) == int(code)))
                    for code in np.unique(np.asarray(runtime_model.cell_type_codes))
                },
                'material_coverage_ratio': float(
                    np.count_nonzero(np.asarray(material_codes) > 0) / max(1, material_codes.size)
                ),
            },
        )
        return CompilationBundle(
            prepared_case=prepared,
            runtime_model=runtime_model,
            partitioned_model=partitioned_model,
            compile_report=report,
        )
