from __future__ import annotations

import numpy as np

from .schemas import DistributedDofNumbering, MeshPartition, RuntimeModel


def build_distributed_numbering(
    runtime_model: RuntimeModel,
    partitions: tuple[MeshPartition, ...],
) -> DistributedDofNumbering:
    dof_per_node = int(runtime_model.dof_per_node)
    node_dof_ids = np.full((int(runtime_model.node_count), dof_per_node), -1, dtype=np.int64)
    owned_ranges: list[tuple[int, int]] = []
    owned_dof_ids: list[np.ndarray] = []
    ghost_dof_ids: list[np.ndarray] = []
    local_to_global: list[np.ndarray] = []
    global_to_local: list[dict[int, int]] = []
    cursor = 0

    for partition in partitions:
        owned_nodes = np.asarray(partition.owned_node_ids, dtype=np.int32)
        count = int(owned_nodes.size) * dof_per_node
        start = int(cursor)
        stop = int(cursor + count)
        owned_ranges.append((start, stop))
        if owned_nodes.size:
            node_dof_ids[owned_nodes] = np.arange(start, stop, dtype=np.int64).reshape(owned_nodes.size, dof_per_node)
        cursor = stop

    for partition in partitions:
        owned_nodes = np.asarray(partition.owned_node_ids, dtype=np.int32)
        ghost_nodes = np.asarray(partition.ghost_node_ids, dtype=np.int32)
        local_nodes = np.concatenate([owned_nodes, ghost_nodes]) if (owned_nodes.size or ghost_nodes.size) else np.asarray([], dtype=np.int32)
        local_to_global.append(local_nodes)
        global_to_local.append({int(node_id): idx for idx, node_id in enumerate(local_nodes.tolist())})
        owned_dof_ids.append(node_dof_ids[owned_nodes].reshape(-1) if owned_nodes.size else np.asarray([], dtype=np.int64))
        ghost_dof_ids.append(node_dof_ids[ghost_nodes].reshape(-1) if ghost_nodes.size else np.asarray([], dtype=np.int64))

    return DistributedDofNumbering(
        dof_per_node=dof_per_node,
        global_dof_count=int(cursor),
        owned_dof_ranges=tuple(owned_ranges),
        local_to_global_node=tuple(local_to_global),
        global_to_local_node_maps=tuple(global_to_local),
        owned_dof_ids=tuple(owned_dof_ids),
        ghost_dof_ids=tuple(ghost_dof_ids),
        metadata={
            'strategy': 'contiguous-owned',
            'node_dof_ids': node_dof_ids,
        },
    )
