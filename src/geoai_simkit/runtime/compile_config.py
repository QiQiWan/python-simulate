from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CompileConfig:
    partition_count: int = 1
    partition_strategy: str = 'graph'
    numbering_strategy: str = 'contiguous-owned'
    enable_halo: bool = True
    enable_stage_masks: bool = True
    target_device_family: str = 'auto'
    memory_budget_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.partition_count = max(1, int(self.partition_count or 1))


@dataclass(slots=True)
class PartitionConfig:
    partition_count: int
    strategy: str = 'graph'
    weight_by_gp_count: bool = True
    weight_by_material_cost: bool = True
    keep_regions_compact: bool = False
    keep_stage_locality: bool = True
    rebalance_policy: str = 'none'
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.partition_count = max(1, int(self.partition_count or 1))


@dataclass(slots=True)
class RuntimeConfig:
    backend: str = 'distributed'
    communicator_backend: str = 'local'
    device_mode: str = 'single'
    partition_count: int = 1
    checkpoint_policy: str = 'stage-and-failure'
    telemetry_level: str = 'standard'
    fail_policy: str = 'rollback-cutback'
    deterministic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.partition_count = max(1, int(self.partition_count or 1))


@dataclass(slots=True)
class SolverPolicy:
    nonlinear_max_iterations: int = 12
    tolerance: float = 1.0e-5
    line_search: bool = True
    max_cutbacks: int = 5
    preconditioner: str = 'auto'
    solver_strategy: str = 'auto'
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.nonlinear_max_iterations = max(1, int(self.nonlinear_max_iterations or 1))
        self.max_cutbacks = max(0, int(self.max_cutbacks or 0))


@dataclass(slots=True)
class ExportPolicy:
    export_model: bool = True
    export_stage_series: bool = True
    export_increment_snapshots: bool = False
    export_runtime_manifest: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FailurePolicy:
    enable_cpu_fallback: bool = False
    rollback_to_stage_start: bool = True
    max_stage_retries: int = 0
    max_increment_cutbacks: int = 5
    write_failure_checkpoint: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.max_stage_retries = max(0, int(self.max_stage_retries or 0))
        self.max_increment_cutbacks = max(0, int(self.max_increment_cutbacks or 0))


@dataclass(slots=True)
class CheckpointPolicy:
    save_at_stage_end: bool = True
    save_at_failure: bool = True
    save_every_n_increments: int = 0
    keep_last_n: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.save_every_n_increments = max(0, int(self.save_every_n_increments or 0))
        self.keep_last_n = max(1, int(self.keep_last_n or 1))


@dataclass(slots=True)
class ReproducibilityConfig:
    deterministic_reduction: bool = False
    fixed_partition_seed: int | None = None
    fixed_ordering_seed: int | None = None
    stable_export_order: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IncrementPlan:
    target_steps: int
    min_step_size: float
    max_step_size: float
    growth_factor: float
    shrink_factor: float
    target_iteration_low: int
    target_iteration_high: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.target_steps = max(1, int(self.target_steps or 1))
        self.min_step_size = max(1.0e-8, float(self.min_step_size or 1.0e-8))
        self.max_step_size = max(self.min_step_size, float(self.max_step_size or self.min_step_size))
        self.target_iteration_low = max(1, int(self.target_iteration_low or 1))
        self.target_iteration_high = max(
            self.target_iteration_low,
            int(self.target_iteration_high or self.target_iteration_low),
        )


@dataclass(slots=True)
class StageStateTransferPolicy:
    inherit_displacement: bool = True
    inherit_material_state: bool = True
    reset_external_load_accumulator: bool = True
    reset_contact_cache: bool = False
    reset_line_search_history: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
