from __future__ import annotations

import numpy as np

from .schemas import DistributedDofNumbering, HaloExchangePlan, MeshPartition


def build_halo_exchange_plans(
    partitions: tuple[MeshPartition, ...],
    numbering: DistributedDofNumbering,
) -> tuple[HaloExchangePlan, ...]:
    node_dof_ids = np.asarray(numbering.metadata.get('node_dof_ids'), dtype=np.int64)
    plans: list[HaloExchangePlan] = []
    partition_map = {part.partition_id: part for part in partitions}
    for partition in partitions:
        recv_neighbors = tuple(int(item) for item in partition.neighbor_partition_ids)
        send_neighbors = recv_neighbors
        send_node_ids: list[np.ndarray] = []
        recv_node_ids: list[np.ndarray] = []
        send_dof_ids: list[np.ndarray] = []
        recv_dof_ids: list[np.ndarray] = []
        owned_set = set(int(node_id) for node_id in np.asarray(partition.owned_node_ids, dtype=np.int32).tolist())
        ghost_set = set(int(node_id) for node_id in np.asarray(partition.ghost_node_ids, dtype=np.int32).tolist())
        for neighbor in recv_neighbors:
            other = partition_map[int(neighbor)]
            other_owned = set(int(node_id) for node_id in np.asarray(other.owned_node_ids, dtype=np.int32).tolist())
            other_ghost = set(int(node_id) for node_id in np.asarray(other.ghost_node_ids, dtype=np.int32).tolist())
            send_nodes = np.asarray(sorted(owned_set & (other_owned | other_ghost)), dtype=np.int32)
            recv_nodes = np.asarray(sorted(ghost_set & other_owned), dtype=np.int32)
            send_node_ids.append(send_nodes)
            recv_node_ids.append(recv_nodes)
            send_dof_ids.append(node_dof_ids[send_nodes].reshape(-1) if send_nodes.size else np.asarray([], dtype=np.int64))
            recv_dof_ids.append(node_dof_ids[recv_nodes].reshape(-1) if recv_nodes.size else np.asarray([], dtype=np.int64))
        plans.append(
            HaloExchangePlan(
                partition_id=partition.partition_id,
                send_neighbors=send_neighbors,
                recv_neighbors=recv_neighbors,
                send_node_ids=tuple(send_node_ids),
                recv_node_ids=tuple(recv_node_ids),
                send_dof_ids=tuple(send_dof_ids),
                recv_dof_ids=tuple(recv_dof_ids),
                metadata={
                    'halo_node_count': int(sum(arr.size for arr in recv_node_ids)),
                    'halo_dof_count': int(sum(arr.size for arr in recv_dof_ids)),
                },
            )
        )
    return tuple(plans)
