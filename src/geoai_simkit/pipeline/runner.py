from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.pipeline.builder import AnalysisCaseBuilder
from geoai_simkit.pipeline.execution import build_execution_plan, build_solver_settings
from geoai_simkit.pipeline.specs import AnalysisCaseSpec, PreparedAnalysisCase
from geoai_simkit.post.exporters import ExportManager
from geoai_simkit.results.runtime_adapter import RuntimeResultStoreAdapter
from geoai_simkit.runtime import CompileConfig, RuntimeCompiler, RuntimeConfig
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.backends import LocalBackend, build_runtime


@dataclass(slots=True)
class AnalysisRunResult:
    prepared: PreparedAnalysisCase
    solved_model: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    compilation_bundle: Any | None = None
    compile_report: Any | None = None
    runtime_report: Any | None = None
    result_store: Any | None = None
    result_db: Any | None = None


@dataclass(slots=True)
class AnalysisExportSpec:
    out_dir: str | Path = 'exports'
    stem: str | None = None
    export_model: bool = True
    export_stage_series: bool = True
    export_runtime_manifest: bool = True


@dataclass(slots=True)
class AnalysisTaskSpec:
    case: AnalysisCaseSpec
    execution_profile: str = 'auto'
    device: str | None = None
    solver_settings: SolverSettings | None = None
    compile_config: CompileConfig | None = None
    runtime_config: RuntimeConfig | None = None
    export: AnalysisExportSpec | None = None


class GeneralFEMSolver:
    def __init__(
        self,
        backend: Any | None = None,
        *,
        compiler: RuntimeCompiler | None = None,
        runtime_factory: Any | None = None,
        result_adapter: Any | None = None,
    ) -> None:
        self.backend = backend if isinstance(backend, LocalBackend) else LocalBackend(backend)
        self.compiler = compiler or RuntimeCompiler()
        self.runtime_factory = runtime_factory or build_runtime
        self.result_adapter = result_adapter or RuntimeResultStoreAdapter()

    def prepare_case(self, spec: AnalysisCaseSpec) -> PreparedAnalysisCase:
        return AnalysisCaseBuilder(spec).build()

    def _resolve_compile_config(
        self,
        settings: SolverSettings,
        *,
        compile_config: CompileConfig | None = None,
    ) -> CompileConfig:
        if compile_config is not None:
            return compile_config
        return CompileConfig(
            partition_count=max(1, int(settings.metadata.get('partition_count', 1) or 1)),
            partition_strategy=str(settings.metadata.get('partition_strategy', 'graph')),
            numbering_strategy='contiguous-owned',
            enable_halo=bool(settings.metadata.get('enable_halo', True)),
            enable_stage_masks=True,
            target_device_family='cuda' if str(settings.device).startswith('cuda') else 'cpu',
            metadata={},
        )

    def _resolve_runtime_config(
        self,
        settings: SolverSettings,
        compile_config: CompileConfig,
        *,
        runtime_config: RuntimeConfig | None = None,
    ) -> RuntimeConfig:
        if runtime_config is not None:
            return runtime_config
        return RuntimeConfig(
            backend='distributed',
            communicator_backend=str(settings.metadata.get('communicator_backend', 'local')),
            device_mode='single' if int(compile_config.partition_count) == 1 else 'multi',
            partition_count=int(compile_config.partition_count),
            checkpoint_policy=str(settings.metadata.get('checkpoint_policy', 'stage-and-failure')),
            telemetry_level=str(settings.metadata.get('telemetry_level', 'standard')),
            fail_policy='rollback-cutback',
            deterministic=bool(settings.metadata.get('deterministic', False)),
            metadata={
                'warp_device': str(settings.metadata.get('warp_device', settings.device)),
                'multi_gpu_mode': str(settings.metadata.get('multi_gpu_mode', 'single')),
                'allowed_gpu_devices': list(settings.metadata.get('allowed_gpu_devices', []) or []),
                'preconditioner': str(settings.metadata.get('preconditioner', 'auto')),
                'solver_strategy': str(settings.metadata.get('solver_strategy', 'auto')),
                'checkpoint_dir': (
                    None
                    if not settings.metadata.get('checkpoint_dir')
                    else str(settings.metadata.get('checkpoint_dir'))
                ),
                'checkpoint_every_n_increments': (
                    None
                    if settings.metadata.get('checkpoint_every_n_increments') in {None, ''}
                    else int(settings.metadata.get('checkpoint_every_n_increments'))
                ),
                'checkpoint_keep_last_n': (
                    None
                    if settings.metadata.get('checkpoint_keep_last_n') in {None, ''}
                    else int(settings.metadata.get('checkpoint_keep_last_n'))
                ),
                'resume_checkpoint_id': (
                    None
                    if not settings.metadata.get('resume_checkpoint_id')
                    else str(settings.metadata.get('resume_checkpoint_id'))
                ),
            },
        )

    def solve_case(
        self,
        spec: AnalysisCaseSpec,
        settings: SolverSettings,
        *,
        compile_config: CompileConfig | None = None,
        runtime_config: RuntimeConfig | None = None,
    ) -> AnalysisRunResult:
        prepared = self.prepare_case(spec)
        compile_cfg = self._resolve_compile_config(settings, compile_config=compile_config)
        runtime_cfg = self._resolve_runtime_config(settings, compile_cfg, runtime_config=runtime_config)
        bundle = self.compiler.compile_case(prepared, compile_cfg)
        if not bundle.compile_report.ok:
            raise ValueError('; '.join(bundle.compile_report.errors) or 'Runtime compilation failed.')
        runtime = self.runtime_factory(runtime_cfg, settings, local_backend=self.backend)
        runtime.initialize(bundle)
        runtime_report = runtime.execute()
        solved = runtime.solved_model
        result_db = self.result_adapter.from_runtime_store(runtime.result_store)
        runtime.shutdown()
        failure_checkpoint_ids = tuple(
            checkpoint_id
            for checkpoint_id in runtime_report.checkpoints
            if str(checkpoint_id).startswith('failure-')
        )
        increment_checkpoint_ids = tuple(
            checkpoint_id
            for checkpoint_id in runtime_report.checkpoints
            if str(checkpoint_id).startswith('increment-')
        )
        solved.metadata.setdefault('pipeline.run_metadata', {})
        solved.metadata['pipeline.run_metadata'].update(
            {
                'case_name': spec.name,
                'prepared_stage_count': len(prepared.model.stages),
                'prepared_interface_count': len(prepared.model.interfaces),
                'compile_report': dict(bundle.compile_report.metadata),
                'partition_advisory': dict(bundle.compile_report.metadata.get('partition_advisory', {}) or {}),
                'telemetry_summary': dict(runtime_report.telemetry_summary),
                'checkpoint_ids': list(runtime_report.checkpoints),
                'increment_checkpoint_ids': list(increment_checkpoint_ids),
                'failure_checkpoint_ids': list(failure_checkpoint_ids),
                'resume_checkpoint_selector': runtime_report.metadata.get('resume_checkpoint_selector'),
                'resumed_from_checkpoint': runtime_report.metadata.get('resumed_from_checkpoint'),
            }
        )
        return AnalysisRunResult(
            prepared=prepared,
            solved_model=solved,
            metadata={
                'case_name': spec.name,
                'prepared_report': prepared.report.metadata,
                'compile_report': dict(bundle.compile_report.metadata),
                'partition_advisory': dict(bundle.compile_report.metadata.get('partition_advisory', {}) or {}),
                'runtime_metadata': dict(runtime_report.metadata),
                'telemetry_summary': dict(runtime_report.telemetry_summary),
                'checkpoint_ids': tuple(runtime_report.checkpoints),
                'increment_checkpoint_ids': increment_checkpoint_ids,
                'failure_checkpoint_ids': failure_checkpoint_ids,
                'resume_checkpoint_selector': runtime_report.metadata.get('resume_checkpoint_selector'),
                'resumed_from_checkpoint': runtime_report.metadata.get('resumed_from_checkpoint'),
            },
            compilation_bundle=bundle,
            compile_report=bundle.compile_report,
            runtime_report=runtime_report,
            result_store=runtime.result_store,
            result_db=result_db,
        )

    def run_task(self, task: AnalysisTaskSpec) -> AnalysisRunResult:
        if task.solver_settings is not None:
            settings = task.solver_settings
            plan = None
        else:
            plan = build_execution_plan(
                task.execution_profile,
                device=task.device,
                partition_count=(task.compile_config.partition_count if task.compile_config is not None else None),
            )
            settings = build_solver_settings(
                task.execution_profile,
                device=task.device,
                partition_count=plan.compile_config.partition_count,
            )
        compile_config = task.compile_config or (plan.compile_config if plan is not None else None)
        runtime_config = task.runtime_config or (plan.runtime_config if plan is not None else None)
        if task.export is not None:
            out_dir = Path(task.export.out_dir)
            stem = task.export.stem or task.case.name
            if runtime_config is None:
                runtime_config = RuntimeConfig(partition_count=(compile_config.partition_count if compile_config is not None else 1))
            runtime_config.metadata.setdefault('checkpoint_dir', str(out_dir / f'{stem}_runtime' / 'checkpoints'))
        result = self.solve_case(task.case, settings, compile_config=compile_config, runtime_config=runtime_config)
        if task.export is not None:
            exporter = ExportManager()
            out_dir.mkdir(parents=True, exist_ok=True)
            if task.export.export_model:
                exporter.export_model(result.solved_model, out_dir / f'{stem}.vtu')
            if task.export.export_stage_series:
                exporter.export_stage_series(result.solved_model, out_dir / f'{stem}_bundle', stem=stem)
            if task.export.export_runtime_manifest and result.runtime_report is not None:
                manifest_path = out_dir / f'{stem}_runtime_manifest.json'
                manifest_path.write_text(
                    __import__('json').dumps(
                        {
                            'case_name': task.case.name,
                            'compile_report': dict(result.compile_report.metadata) if result.compile_report is not None else {},
                            'telemetry_summary': dict(result.runtime_report.telemetry_summary),
                            'checkpoint_ids': list(result.runtime_report.checkpoints),
                            'increment_checkpoint_ids': list(
                                result.runtime_report.metadata.get('increment_checkpoint_ids', ())
                            ),
                            'failure_checkpoint_ids': list(
                                result.runtime_report.metadata.get('failure_checkpoint_ids', ())
                            ),
                            'partition_advisory': dict(
                                result.runtime_report.metadata.get('partition_advisory', {}) or {}
                            ),
                            'runtime_metadata': dict(result.runtime_report.metadata),
                            'stage_asset_count': len(getattr(result.result_store, 'stage_assets', []) or []),
                            'stage_linear_system_diagnostics_count': int(
                                result.runtime_report.metadata.get(
                                    'stage_linear_system_diagnostics_count',
                                    0,
                                )
                                or 0
                            ),
                            'stage_assets': [
                                dict(item)
                                for item in getattr(result.result_store, 'stage_assets', []) or []
                            ],
                            'stage_linear_system_plans': list(
                                result.runtime_report.metadata.get('stage_linear_system_plans', ())
                            ),
                            'linear_system_diagnostics_summary': dict(
                                result.runtime_report.metadata.get(
                                    'linear_system_diagnostics_summary',
                                    {},
                                )
                                or {}
                            ),
                            'checkpoint_policy': dict(
                                result.runtime_report.metadata.get('checkpoint_policy', {}) or {}
                            ),
                            'checkpoint_dir': result.runtime_report.metadata.get('checkpoint_dir'),
                            'resume_checkpoint_selector': result.runtime_report.metadata.get('resume_checkpoint_selector'),
                            'resumed_from_checkpoint': result.runtime_report.metadata.get('resumed_from_checkpoint'),
                            'resume_checkpoint_kind': result.runtime_report.metadata.get('resume_checkpoint_kind'),
                            'stage_reports': [
                                {
                                    'stage_name': report.stage_name,
                                    'status': report.status,
                                    'active_cell_count': report.active_cell_count,
                                    'increment_count': report.increment_count,
                                    'iteration_count': report.iteration_count,
                                }
                                for report in result.runtime_report.stage_reports
                            ],
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding='utf-8',
                )
        return result
