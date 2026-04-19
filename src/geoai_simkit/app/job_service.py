from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.pipeline import AnalysisCaseSpec, AnalysisExportSpec, AnalysisTaskSpec, GeneralFEMSolver, build_execution_plan, build_solver_settings
from geoai_simkit.results import ResultDatabase, build_result_database, build_result_database_from_runtime_store
from geoai_simkit.runtime import RuntimeCompiler


@dataclass(slots=True)
class JobPlanSummary:
    case_name: str
    profile: str
    device: str
    has_cuda: bool
    thread_count: int
    note: str
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_partitions: int | None = None
    estimated_peak_memory_bytes: int | None = None
    partition_advisory: dict[str, Any] = field(default_factory=dict)
    stage_execution_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobRunSummary:
    case_name: str
    profile: str
    device: str
    out_path: Path | None
    stage_count: int
    field_count: int
    result_db: ResultDatabase
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: tuple[str, ...] = ()
    increment_checkpoint_ids: tuple[str, ...] = ()
    failure_checkpoint_ids: tuple[str, ...] = ()
    telemetry_summary: dict[str, object] = field(default_factory=dict)
    compile_report: dict[str, object] = field(default_factory=dict)
    partition_advisory: dict[str, object] = field(default_factory=dict)
    runtime_metadata: dict[str, object] = field(default_factory=dict)
    runtime_manifest_path: Path | None = None


class JobService:
    def plan_case(
        self,
        case: AnalysisCaseSpec,
        *,
        execution_profile: str = 'auto',
        device: str | None = None,
        partition_count: int | None = None,
        communicator_backend: str = 'local',
        checkpoint_policy: str = 'stage-and-failure',
        checkpoint_dir: str | None = None,
        checkpoint_every_n_increments: int | None = None,
        checkpoint_keep_last_n: int | None = None,
        max_cutbacks: int | None = None,
        max_stage_retries: int | None = None,
        telemetry_level: str = 'standard',
        deterministic: bool = False,
        resume_checkpoint_id: str | None = None,
    ) -> JobPlanSummary:
        solver = GeneralFEMSolver()
        plan = build_execution_plan(
            execution_profile,
            device=device,
            partition_count=partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
        )
        prepared = solver.prepare_case(case)
        bundle = RuntimeCompiler().compile_case(prepared, plan.compile_config)
        solver_settings = build_solver_settings(
            execution_profile,
            device=device,
            partition_count=plan.compile_config.partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
        )
        stage_execution_diagnostics = dict(
            solver.backend.stage_execution_diagnostics(prepared.model, solver_settings)
        )
        metadata = dict(plan.metadata)
        metadata['compile_report'] = dict(bundle.compile_report.metadata)
        metadata['stage_execution_diagnostics'] = dict(stage_execution_diagnostics)
        return JobPlanSummary(
            case_name=case.name,
            profile=plan.profile,
            device=plan.device,
            has_cuda=plan.has_cuda,
            thread_count=plan.thread_count,
            note=plan.note,
            metadata=metadata,
            estimated_partitions=int(bundle.compile_report.metadata.get('partition_count', plan.compile_config.partition_count)),
            estimated_peak_memory_bytes=int(bundle.compile_report.metadata.get('estimated_peak_memory_bytes', 0) or 0),
            partition_advisory=dict(bundle.compile_report.metadata.get('partition_advisory', {}) or {}),
            stage_execution_diagnostics=stage_execution_diagnostics,
        )

    def run_case(
        self,
        case: AnalysisCaseSpec,
        out_dir: Path,
        *,
        execution_profile: str = 'auto',
        device: str | None = None,
        export_stage_series: bool = True,
        partition_count: int | None = None,
        communicator_backend: str = 'local',
        checkpoint_policy: str = 'stage-and-failure',
        checkpoint_dir: str | None = None,
        checkpoint_every_n_increments: int | None = None,
        checkpoint_keep_last_n: int | None = None,
        max_cutbacks: int | None = None,
        max_stage_retries: int | None = None,
        telemetry_level: str = 'standard',
        deterministic: bool = False,
        resume_checkpoint_id: str | None = None,
    ) -> JobRunSummary:
        plan = build_execution_plan(
            execution_profile,
            device=device,
            partition_count=partition_count,
            communicator_backend=communicator_backend,
            checkpoint_policy=checkpoint_policy,
            checkpoint_dir=checkpoint_dir,
            checkpoint_every_n_increments=checkpoint_every_n_increments,
            checkpoint_keep_last_n=checkpoint_keep_last_n,
            max_cutbacks=max_cutbacks,
            max_stage_retries=max_stage_retries,
            telemetry_level=telemetry_level,
            deterministic=deterministic,
            resume_checkpoint_id=resume_checkpoint_id,
        )
        task = AnalysisTaskSpec(case=case, execution_profile=execution_profile, device=device, compile_config=plan.compile_config, runtime_config=plan.runtime_config, export=AnalysisExportSpec(out_dir=out_dir, stem=case.name, export_model=True, export_stage_series=export_stage_series, export_runtime_manifest=True))
        result = GeneralFEMSolver().run_task(task)
        if result.result_store is not None:
            db = build_result_database_from_runtime_store(result.result_store)
        elif result.result_db is not None:
            db = result.result_db
        else:
            db = build_result_database(result.solved_model)
        out_path = out_dir / f'{case.name}.vtu'
        return JobRunSummary(
            case_name=case.name,
            profile=execution_profile,
            device=device or 'auto',
            out_path=out_path,
            stage_count=len(db.stage_names()),
            field_count=len(db.fields),
            result_db=db,
            metadata=dict(result.metadata),
            checkpoint_ids=tuple(result.metadata.get('checkpoint_ids', ()) or ()),
            increment_checkpoint_ids=tuple(result.metadata.get('increment_checkpoint_ids', ()) or ()),
            failure_checkpoint_ids=tuple(result.metadata.get('failure_checkpoint_ids', ()) or ()),
            telemetry_summary=dict(result.metadata.get('telemetry_summary', {}) or {}),
            compile_report=dict(result.metadata.get('compile_report', {}) or {}),
            partition_advisory=dict(result.metadata.get('partition_advisory', {}) or {}),
            runtime_metadata=dict(result.metadata.get('runtime_metadata', {}) or {}),
            runtime_manifest_path=out_dir / f'{case.name}_runtime_manifest.json',
        )


__all__ = ['JobPlanSummary', 'JobRunSummary', 'JobService']
