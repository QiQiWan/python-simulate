from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .compile_config import IncrementPlan


@dataclass(slots=True)
class StageActivationMask:
    active_region_codes: Any
    active_cell_mask: Any
    active_structure_mask: Any
    active_interface_mask: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompiledStagePlan:
    stage_names: tuple[str, ...]
    topo_order: tuple[int, ...]
    predecessor_index: tuple[int, ...]
    activation_masks: tuple[StageActivationMask, ...]
    bc_tables: tuple[Any, ...]
    load_tables: tuple[Any, ...]
    structure_masks: tuple[Any, ...]
    interface_masks: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def stage_index(self, name: str) -> int:
        for idx, stage_name in enumerate(self.stage_names):
            if stage_name == name:
                return idx
        raise KeyError(f'Unknown stage: {name}')


@dataclass(slots=True)
class RuntimeModel:
    name: str
    mesh_kind: str
    node_count: int
    cell_count: int
    spatial_dim: int
    dof_per_node: int
    node_coords: Any
    cell_conn: Any
    cell_arity: Any
    cell_type_codes: Any
    region_codes: Any
    material_codes: Any
    bc_table: Any
    load_table: Any
    structure_table: Any
    interface_table: Any
    stage_plan: CompiledStagePlan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MeshPartition:
    partition_id: int
    owned_cell_ids: Any
    owned_node_ids: Any
    ghost_node_ids: Any
    boundary_face_ids: Any
    neighbor_partition_ids: tuple[int, ...]
    local_node_coords: Any
    local_cell_conn: Any
    local_cell_type_codes: Any
    local_region_codes: Any
    local_material_codes: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DistributedDofNumbering:
    dof_per_node: int
    global_dof_count: int
    owned_dof_ranges: tuple[tuple[int, int], ...]
    local_to_global_node: tuple[Any, ...]
    global_to_local_node_maps: tuple[dict[int, int], ...]
    owned_dof_ids: tuple[Any, ...]
    ghost_dof_ids: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DofConstraintTable:
    constrained_global_dofs: Any
    constrained_values: Any
    elimination_map: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PartitionCommunicationGraph:
    partition_ids: tuple[int, ...]
    neighbor_pairs: tuple[tuple[int, int], ...]
    shared_node_counts: dict[tuple[int, int], int]
    shared_face_counts: dict[tuple[int, int], int]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HaloExchangePlan:
    partition_id: int
    send_neighbors: tuple[int, ...]
    recv_neighbors: tuple[int, ...]
    send_node_ids: tuple[Any, ...]
    recv_node_ids: tuple[Any, ...]
    send_dof_ids: tuple[Any, ...]
    recv_dof_ids: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryBudgetEstimate:
    geometry_bytes: int
    field_bytes: int
    gp_state_bytes: int
    linear_system_bytes: int
    halo_bytes: int
    checkpoint_peak_bytes: int
    total_peak_bytes: int


@dataclass(slots=True)
class PartitionedRuntimeModel:
    global_model: RuntimeModel
    partitions: tuple[MeshPartition, ...]
    numbering: DistributedDofNumbering
    communication_graph: PartitionCommunicationGraph
    halo_plans: tuple[HaloExchangePlan, ...]
    stage_plan: CompiledStagePlan
    memory_estimate: MemoryBudgetEstimate | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeExecutionState:
    current_stage_index: int = 0
    current_increment: int = 0
    committed_stage_index: int = -1
    committed_increment: int = -1
    wallclock_seconds: float = 0.0
    last_checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PartitionExecutionState:
    partition_id: int
    u: Any
    du: Any
    residual: Any
    velocity: Any | None = None
    acceleration: Any | None = None
    material_states: dict[str, Any] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RankContext:
    rank: int
    world_size: int
    local_rank: int
    partition_id: int
    hostname: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeviceContext:
    device_kind: str
    device_name: str
    device_alias: str
    memory_limit_bytes: int | None = None
    stream_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeStageContext:
    stage_index: int
    stage_name: str
    activation_mask: StageActivationMask
    bc_table: object
    load_table: object
    structure_mask: object
    interface_mask: object
    increment_plan: IncrementPlan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GlobalReductionSummary:
    residual_norm: float
    correction_norm: float
    energy_norm: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SynchronizationToken:
    stage_index: int
    increment_index: int
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)
