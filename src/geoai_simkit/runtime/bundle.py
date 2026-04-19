from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import PartitionedRuntimeModel, RuntimeModel


@dataclass(slots=True)
class CompileReport:
    ok: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompilationBundle:
    prepared_case: Any
    runtime_model: RuntimeModel
    partitioned_model: PartitionedRuntimeModel
    compile_report: CompileReport


@dataclass(slots=True)
class StageRunReport:
    stage_index: int
    stage_name: str
    ok: bool
    status: str = 'completed'
    active_cell_count: int = 0
    active_region_count: int = 0
    increment_count: int = 0
    iteration_count: int = 0
    field_names: tuple[str, ...] = ()
    checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeExecutionReport:
    ok: bool
    stage_reports: tuple[StageRunReport, ...]
    telemetry_summary: dict[str, object]
    checkpoints: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
