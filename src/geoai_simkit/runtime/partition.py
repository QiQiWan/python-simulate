from __future__ import annotations

from dataclasses import replace

import numpy as np

from .compile_config import PartitionConfig
from .schemas import MeshPartition, PartitionCommunicationGraph, RuntimeModel


def _partition_slices(cell_count: int, partition_count: int) -> list[np.ndarray]:
    if cell_count <= 0:
        return [np.asarray([], dtype=np.int32)]
    count = max(1, min(int(partition_count or 1), cell_count))
    return [np.asarray(chunk, dtype=np.int32) for chunk in np.array_split(np.arange(cell_count, dtype=np.int32), count)]


def _estimate_cell_gp_counts(runtime_model: RuntimeModel) -> np.ndarray:
    cell_arity = np.asarray(runtime_model.cell_arity, dtype=np.int16).reshape(-1)
    cell_type_codes = np.asarray(runtime_model.cell_type_codes, dtype=np.int16).reshape(-1)
    count = max(int(runtime_model.cell_count), int(cell_arity.size), int(cell_type_codes.size))
    gp_counts = np.ones(count, dtype=np.int32)
    for index in range(count):
        arity = int(cell_arity[index]) if index < cell_arity.size else -1
        cell_type = int(cell_type_codes[index]) if index < cell_type_codes.size else -1
        if cell_type == 12 or arity == 8:
            gp_counts[index] = 8
        elif cell_type == 10 or arity == 4:
            gp_counts[index] = 1
    return gp_counts


def build_partitions(runtime_model: RuntimeModel, config: PartitionConfig) -> tuple[tuple[MeshPartition, ...], PartitionCommunicationGraph]:
    conn = np.asarray(runtime_model.cell_conn, dtype=np.int32)
    gp_counts_by_cell = _estimate_cell_gp_counts(runtime_model)
    cell_ids_by_partition = _partition_slices(int(runtime_model.cell_count), int(config.partition_count))
    partition_count = len(cell_ids_by_partition)
    node_to_partitions: list[set[int]] = [set() for _ in range(int(runtime_model.node_count))]
    for partition_id, owned_cell_ids in enumerate(cell_ids_by_partition):
        for cell_id in owned_cell_ids:
            nodes = conn[int(cell_id)]
            for node_id in nodes[nodes >= 0]:
                node_to_partitions[int(node_id)].add(partition_id)

    node_owner = np.full(int(runtime_model.node_count), -1, dtype=np.int32)
    for node_id, partitions in enumerate(node_to_partitions):
        if partitions:
            node_owner[node_id] = min(partitions)

    partitions: list[MeshPartition] = []
    shared_node_counts: dict[tuple[int, int], int] = {}
    for partition_id, owned_cell_ids in enumerate(cell_ids_by_partition):
        owned_cell_ids = np.asarray(owned_cell_ids, dtype=np.int32)
        local_nodes = np.unique(conn[owned_cell_ids][conn[owned_cell_ids] >= 0]) if owned_cell_ids.size else np.asarray([], dtype=np.int32)
        owned_node_ids = np.asarray(
            [int(node_id) for node_id in local_nodes if node_owner[int(node_id)] == partition_id],
            dtype=np.int32,
        )
        ghost_node_ids = np.asarray(
            [int(node_id) for node_id in local_nodes if node_owner[int(node_id)] != partition_id],
            dtype=np.int32,
        )
        local_order = np.concatenate([owned_node_ids, ghost_node_ids]) if (owned_node_ids.size or ghost_node_ids.size) else np.asarray([], dtype=np.int32)
        local_map = {int(node_id): idx for idx, node_id in enumerate(local_order.tolist())}
        local_conn = np.full((owned_cell_ids.size, conn.shape[1]), -1, dtype=np.int32)
        if owned_cell_ids.size:
            for local_cell_idx, global_cell_id in enumerate(owned_cell_ids.tolist()):
                for local_node_slot, global_node_id in enumerate(conn[int(global_cell_id)].tolist()):
                    if int(global_node_id) >= 0:
                        local_conn[local_cell_idx, local_node_slot] = int(local_map[int(global_node_id)])

        neighbors = sorted(
            {
                other
                for node_id in local_nodes.tolist()
                for other in node_to_partitions[int(node_id)]
                if other != partition_id
            }
        )
        for other in neighbors:
            key = (min(partition_id, other), max(partition_id, other))
            if key not in shared_node_counts:
                other_nodes = set(
                    int(node_id)
                    for node_id, owners in enumerate(node_to_partitions)
                    if partition_id in owners and other in owners
                )
                shared_node_counts[key] = len(other_nodes)

        partitions.append(
            MeshPartition(
                partition_id=partition_id,
                owned_cell_ids=owned_cell_ids,
                owned_node_ids=owned_node_ids,
                ghost_node_ids=ghost_node_ids,
                boundary_face_ids=np.asarray([], dtype=np.int32),
                neighbor_partition_ids=tuple(int(item) for item in neighbors),
                local_node_coords=np.asarray(runtime_model.node_coords[local_order], dtype=float) if local_order.size else np.empty((0, int(runtime_model.spatial_dim)), dtype=float),
                local_cell_conn=local_conn,
                local_cell_type_codes=np.asarray(runtime_model.cell_type_codes[owned_cell_ids], dtype=np.int16),
                local_region_codes=np.asarray(runtime_model.region_codes[owned_cell_ids], dtype=np.int16),
                local_material_codes=np.asarray(runtime_model.material_codes[owned_cell_ids], dtype=np.int16),
                metadata={
                    'owned_cell_count': int(owned_cell_ids.size),
                    'gp_state_count': int(np.asarray(gp_counts_by_cell[owned_cell_ids], dtype=np.int32).sum()) if owned_cell_ids.size else 0,
                    'owned_node_count': int(owned_node_ids.size),
                    'ghost_node_count': int(ghost_node_ids.size),
                    'local_node_order': local_order,
                    'node_owner': node_owner.copy(),
                    'rebalance_policy': config.rebalance_policy,
                },
            )
        )

    cell_balance_ratio = 1.0
    node_balance_ratio = 1.0
    dof_balance_ratio = 1.0
    ghost_node_ratio = 0.0
    if partitions:
        cell_counts = [max(1, int(part.metadata.get('owned_cell_count', 0))) for part in partitions]
        node_counts = [max(1, int(part.metadata.get('owned_node_count', 0))) for part in partitions]
        dof_counts = [
            max(1, int(part.metadata.get('owned_node_count', 0)) * int(runtime_model.dof_per_node))
            for part in partitions
        ]
        total_owned_nodes = sum(int(part.metadata.get('owned_node_count', 0)) for part in partitions)
        total_ghost_nodes = sum(int(part.metadata.get('ghost_node_count', 0)) for part in partitions)
        cell_balance_ratio = max(cell_counts) / max(1, min(cell_counts))
        node_balance_ratio = max(node_counts) / max(1, min(node_counts))
        dof_balance_ratio = max(dof_counts) / max(1, min(dof_counts))
        ghost_node_ratio = float(total_ghost_nodes / max(1, total_owned_nodes))
    graph = PartitionCommunicationGraph(
        partition_ids=tuple(part.partition_id for part in partitions),
        neighbor_pairs=tuple(sorted(shared_node_counts.keys())),
        shared_node_counts=shared_node_counts,
        shared_face_counts={key: 0 for key in shared_node_counts},
        metadata={
            'partition_strategy': config.strategy,
            'cell_balance_ratio': float(cell_balance_ratio),
            'node_balance_ratio': float(node_balance_ratio),
            'dof_balance_ratio': float(dof_balance_ratio),
            'ghost_node_ratio': float(ghost_node_ratio),
            'cells_per_partition': [int(part.metadata.get('owned_cell_count', 0)) for part in partitions],
            'gp_states_per_partition': [int(part.metadata.get('gp_state_count', 0)) for part in partitions],
            'owned_nodes_per_partition': [int(part.metadata.get('owned_node_count', 0)) for part in partitions],
            'ghost_nodes_per_partition': [int(part.metadata.get('ghost_node_count', 0)) for part in partitions],
            'owned_dofs_per_partition': [
                int(part.metadata.get('owned_node_count', 0)) * int(runtime_model.dof_per_node)
                for part in partitions
            ],
        },
    )
    for index, part in enumerate(partitions):
        partitions[index] = replace(
            part,
            metadata={
                **part.metadata,
                'cell_balance_ratio': float(cell_balance_ratio),
                'node_balance_ratio': float(node_balance_ratio),
                'dof_balance_ratio': float(dof_balance_ratio),
                'ghost_node_ratio': float(ghost_node_ratio),
                'owned_dof_count': int(part.metadata.get('owned_node_count', 0)) * int(runtime_model.dof_per_node),
                'gp_state_count': int(part.metadata.get('gp_state_count', 0) or 0),
                'neighbor_count': len(part.neighbor_partition_ids),
            },
        )
    return tuple(partitions), graph
