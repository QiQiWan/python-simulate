from __future__ import annotations

import socket
from dataclasses import dataclass

import numpy as np

from geoai_simkit.solver.gpu_runtime import bind_rank_device, device_capacity_snapshot

from .compile_config import RuntimeConfig
from .schemas import DeviceContext, PartitionExecutionState, RankContext


@dataclass(slots=True)
class RuntimeBootstrapState:
    rank_contexts: tuple[RankContext, ...]
    device_contexts: tuple[DeviceContext, ...]
    partition_states: tuple[PartitionExecutionState, ...]


class RuntimeBootstrapper:
    def bootstrap(self, bundle, config: RuntimeConfig) -> RuntimeBootstrapState:
        host = socket.gethostname()
        device_snapshot = device_capacity_snapshot(
            allowed_devices=config.metadata.get('allowed_gpu_devices'),
        )
        rank_contexts: list[RankContext] = []
        device_contexts: list[DeviceContext] = []
        partition_states: list[PartitionExecutionState] = []
        for partition in bundle.partitioned_model.partitions:
            device_alias = bind_rank_device(
                partition.partition_id,
                config.metadata.get('warp_device') or 'cpu',
                allowed_devices=config.metadata.get('allowed_gpu_devices'),
                multi_gpu_mode=config.metadata.get('multi_gpu_mode'),
            )
            device_info = next(
                (item for item in device_snapshot if item.get('alias') == device_alias),
                {'alias': device_alias, 'name': device_alias, 'memory_bytes': 0},
            )
            rank_contexts.append(
                RankContext(
                    rank=partition.partition_id,
                    world_size=len(bundle.partitioned_model.partitions),
                    local_rank=partition.partition_id,
                    partition_id=partition.partition_id,
                    hostname=host,
                )
            )
            device_contexts.append(
                DeviceContext(
                    device_kind='cuda' if str(device_alias).startswith('cuda') else 'cpu',
                    device_name=str(device_info.get('name') or device_alias),
                    device_alias=str(device_alias),
                    memory_limit_bytes=int(device_info.get('memory_bytes') or 0) or None,
                )
            )
            node_count = int(np.asarray(partition.local_node_coords).shape[0])
            dof_per_node = int(bundle.runtime_model.dof_per_node)
            ndof = node_count * dof_per_node
            partition_states.append(
                PartitionExecutionState(
                    partition_id=partition.partition_id,
                    u=np.zeros(ndof, dtype=float),
                    du=np.zeros(ndof, dtype=float),
                    residual=np.zeros(ndof, dtype=float),
                    metadata={
                        'owned_cell_count': int(np.asarray(partition.owned_cell_ids).size),
                    },
                )
            )
        return RuntimeBootstrapState(
            rank_contexts=tuple(rank_contexts),
            device_contexts=tuple(device_contexts),
            partition_states=tuple(partition_states),
        )
