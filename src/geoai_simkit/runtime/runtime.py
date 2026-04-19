from __future__ import annotations

import copy
from time import perf_counter
from typing import Any

import numpy as np

from geoai_simkit.core.model import AnalysisStage

from .bootstrap import RuntimeBootstrapper
from .bundle import RuntimeExecutionReport, StageRunReport
from .compile_config import FailurePolicy, RuntimeConfig, SolverPolicy
from .communicator import make_communicator
from .nonlinear import NonlinearController
from .result_store import RuntimeResultStore
from .schemas import PartitionExecutionState, RuntimeExecutionState, RuntimeStageContext
from .stage_executor import StageExecutor
from .telemetry import TelemetryRecorder


class DistributedRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        solver_settings: Any,
        local_backend: Any,
        communicator=None,
        telemetry: TelemetryRecorder | None = None,
        checkpoint_manager=None,
        bootstrapper: RuntimeBootstrapper | None = None,
        result_store: RuntimeResultStore | None = None,
    ):
        self.config = config
        self.solver_settings = solver_settings
        self.local_backend = local_backend
        self.communicator = communicator or make_communicator(config.communicator_backend)
        self.telemetry = telemetry or TelemetryRecorder(level=config.telemetry_level)
        self.execution_state = RuntimeExecutionState()
        self._bundle = None
        self._bootstrapper = bootstrapper or RuntimeBootstrapper()
        self.bootstrap = None
        self.result_store = result_store or RuntimeResultStore(metadata={'runtime_backend': config.backend})
        failure_policy = FailurePolicy(
            enable_cpu_fallback=bool(config.metadata.get('enable_cpu_fallback', False)),
            rollback_to_stage_start=bool(config.metadata.get('rollback_to_stage_start', True)),
            max_stage_retries=int(config.metadata.get('max_stage_retries', 0) or 0),
            max_increment_cutbacks=int(config.metadata.get('max_cutbacks', solver_settings.max_cutbacks)),
        )
        solver_policy = SolverPolicy(
            nonlinear_max_iterations=int(solver_settings.max_iterations),
            tolerance=float(solver_settings.tolerance),
            line_search=bool(solver_settings.line_search),
            max_cutbacks=int(solver_settings.max_cutbacks),
            preconditioner=str(config.metadata.get('preconditioner', 'auto')),
            solver_strategy=str(config.metadata.get('solver_strategy', 'auto')),
        )
        nonlinear_controller = NonlinearController(
            solver_policy=solver_policy,
            failure_policy=failure_policy,
        )
        self.checkpoint_manager = checkpoint_manager
        self.stage_executor = StageExecutor(
            nonlinear_controller=nonlinear_controller,
            checkpoint_manager=self.checkpoint_manager,
            telemetry=self.telemetry,
            result_store=self.result_store,
        )
        self.solved_model = None
        self.backend_state = None
        self.stage_execution_supported = False
        self.partition_states: list[PartitionExecutionState] = []
        self.resume_checkpoint_id: str | None = None
        self.resume_checkpoint_selector: str | None = None
        self.resume_checkpoint_kind: str | None = None
        self.resume_checkpoint_validation: dict[str, Any] | None = None
        self.resume_checkpoint_payload: dict[str, Any] | None = None
        self.resume_stage_reports: list[StageRunReport] = []
        self.last_reduction_summary: dict[str, object] = {}
        self.stage_execution_diagnostics: dict[str, object] = {}

    def _bootstrap_summary(self) -> dict[str, object]:
        if self.bootstrap is None:
            return {}
        return {
            'rank_contexts': [
                {
                    'rank': int(ctx.rank),
                    'world_size': int(ctx.world_size),
                    'local_rank': int(ctx.local_rank),
                    'partition_id': int(ctx.partition_id),
                    'hostname': str(ctx.hostname),
                }
                for ctx in self.bootstrap.rank_contexts
            ],
            'device_contexts': [
                {
                    'device_kind': str(ctx.device_kind),
                    'device_name': str(ctx.device_name),
                    'device_alias': str(ctx.device_alias),
                    'memory_limit_bytes': None if ctx.memory_limit_bytes is None else int(ctx.memory_limit_bytes),
                }
                for ctx in self.bootstrap.device_contexts
            ],
            'bootstrap_partition_states': [
                {
                    'partition_id': int(state.partition_id),
                    'owned_cell_count': int(state.metadata.get('owned_cell_count', 0) or 0),
                    'ndof': int(np.asarray(state.u).size),
                }
                for state in self.bootstrap.partition_states
            ],
        }

    def initialize(self, bundle):
        self._bundle = bundle
        self.bootstrap = self._bootstrapper.bootstrap(bundle, self.config)
        self.result_store.metadata.update(
            {
                'case_name': bundle.prepared_case.model.name,
                'partition_count': len(bundle.partitioned_model.partitions),
                'compile_metadata': dict(bundle.compile_report.metadata),
                'linear_system_partition_estimates': list(
                    bundle.compile_report.metadata.get('linear_system_partition_estimates', []) or []
                ),
                'stage_linear_system_plans': list(
                    bundle.compile_report.metadata.get('stage_linear_system_plans', []) or []
                ),
                'bootstrap_summary': self._bootstrap_summary(),
            }
        )
        dof_per_node = int(bundle.runtime_model.dof_per_node)
        self.partition_states = []
        for partition_id, partition in enumerate(bundle.partitioned_model.partitions):
            local_node_count = len(bundle.partitioned_model.numbering.local_to_global_node[partition_id])
            shape = (local_node_count, dof_per_node)
            self.partition_states.append(
                PartitionExecutionState(
                    partition_id=partition.partition_id,
                    u=np.zeros(shape, dtype=float),
                    du=np.zeros(shape, dtype=float),
                    residual=np.zeros(shape, dtype=float),
                    metadata={
                        'neighbor_count': len(partition.neighbor_partition_ids),
                        'ghost_node_count': int(len(np.asarray(partition.ghost_node_ids).reshape(-1))),
                    },
                )
            )
        self.stage_execution_supported = self.local_backend.supports_stage_execution(
            bundle.prepared_case.model,
            self.solver_settings,
        )
        self.stage_execution_diagnostics = dict(
            self.local_backend.stage_execution_diagnostics(
                bundle.prepared_case.model,
                self.solver_settings,
            )
        )
        self.result_store.metadata['stage_execution_diagnostics'] = dict(self.stage_execution_diagnostics)
        requested_resume = str(self.config.metadata.get('resume_checkpoint_id') or '').strip()
        if requested_resume and not self.stage_execution_supported:
            raise RuntimeError('Resume from checkpoint currently requires a stage-aware backend.')
        resolved_resume = None
        if requested_resume and self.checkpoint_manager is not None:
            validation = self.checkpoint_manager.validate_checkpoint(requested_resume)
            self.resume_checkpoint_validation = dict(validation)
            self.config.metadata['resume_checkpoint_validation'] = dict(validation)
            if not bool(validation.get('ok', False)):
                issues = [str(item) for item in validation.get('issues', []) or []]
                issue_text = '; '.join(issues[:3]) if issues else 'unknown restart contract issue'
                raise RuntimeError(
                    f"Resume checkpoint '{requested_resume}' failed validation: {issue_text}"
                )
            resolved_resume = str(validation.get('checkpoint_id') or requested_resume)
        if self.stage_execution_supported:
            self.backend_state = self.local_backend.initialize_runtime_state(
                bundle.prepared_case.model,
                self.solver_settings,
            )
        if requested_resume:
            resolved_resume = (
                requested_resume
                if self.checkpoint_manager is None
                else str(resolved_resume or self.checkpoint_manager.resolve_checkpoint_id(requested_resume))
            )
            self.resume_checkpoint_selector = requested_resume
            self.config.metadata['resolved_resume_checkpoint_id'] = resolved_resume
            self._restore_from_checkpoint(resolved_resume)
        self.telemetry.record_event(
            'runtime-initialize',
            {
                'partition_count': len(bundle.partitioned_model.partitions),
                'communicator_backend': self.config.communicator_backend,
                'stage_execution_supported': bool(self.stage_execution_supported),
                'stage_execution_backend': self.stage_execution_diagnostics.get('backend'),
                'resume_checkpoint_id': requested_resume or None,
                'resolved_resume_checkpoint_id': self.resume_checkpoint_id,
                'resume_checkpoint_validation_ok': (
                    None
                    if self.resume_checkpoint_validation is None
                    else bool(self.resume_checkpoint_validation.get('ok', False))
                ),
                'resume_checkpoint_validation_issue_count': (
                    0
                    if self.resume_checkpoint_validation is None
                    else len(self.resume_checkpoint_validation.get('issues', []) or [])
                ),
            },
        )

    def _runtime_arrays(self) -> dict[str, np.ndarray]:
        if self.backend_state is None:
            return {}
        return self.local_backend.capture_runtime_arrays(self.backend_state)

    def _runtime_resume_payload(self) -> dict[str, object]:
        if self.backend_state is None:
            return {}
        return self.local_backend.capture_runtime_resume_payload(self.backend_state)

    def _hydrate_model_results_from_store(self, model) -> None:
        model.clear_results()
        for field in self.result_store.to_result_fields():
            model.add_result(field)

    def _stage_reports_from_checkpoint(self, payload: dict[str, Any]) -> list[StageRunReport]:
        result_store_payload = dict(payload.get('result_store', {}) or {})
        reports: list[StageRunReport] = []
        for item in result_store_payload.get('stage_summaries', []) or []:
            summary = dict(item)
            reports.append(
                StageRunReport(
                    stage_index=int(summary.get('stage_index', len(reports))),
                    stage_name=str(summary.get('stage_name', f'stage-{len(reports)}')),
                    ok=str(summary.get('status', 'completed')) != 'failed',
                    status='restored',
                    active_cell_count=int(summary.get('active_cell_count', 0)),
                    active_region_count=int(summary.get('active_region_count', 0)),
                    increment_count=int(summary.get('increment_count', 0)),
                    iteration_count=int(summary.get('iteration_count', 0)),
                    field_names=tuple(summary.get('field_names', ()) or ()),
                    checkpoint_id=self.resume_checkpoint_id,
                    metadata={
                        'execution_path': 'restored-from-checkpoint',
                    },
                )
            )
        return reports

    def _restore_from_checkpoint(self, checkpoint_id: str) -> None:
        if self.checkpoint_manager is None:
            raise RuntimeError('Checkpoint manager is required to restore runtime state.')
        payload = self.checkpoint_manager.load_checkpoint(checkpoint_id)
        arrays = dict(payload.get('arrays', {}) or {})
        checkpoint_kind = str(payload.get('kind') or 'stage')
        execution_payload = dict(payload.get('execution_state', {}) or {})
        self.execution_state.current_stage_index = int(execution_payload.get('current_stage_index', 0) or 0)
        self.execution_state.current_increment = int(execution_payload.get('current_increment', 0) or 0)
        self.execution_state.committed_stage_index = int(execution_payload.get('committed_stage_index', -1) or -1)
        self.execution_state.committed_increment = int(execution_payload.get('committed_increment', -1) or -1)
        self.execution_state.wallclock_seconds = float(execution_payload.get('wallclock_seconds', 0.0) or 0.0)
        self.execution_state.last_checkpoint_id = str(
            execution_payload.get('last_checkpoint_id') or checkpoint_id
        )
        if self.backend_state is not None:
            restore_payload = dict(payload.get('backend_resume_state', {}) or {})
            restore_payload.setdefault('checkpoint_kind', checkpoint_kind)
            restore_payload.setdefault(
                'resume_mode',
                'rollback-stage-start' if checkpoint_kind == 'failure' else 'restore-checkpoint',
            )
            self.local_backend.restore_runtime_state(
                self.backend_state,
                arrays=arrays,
                payload=restore_payload,
            )
        if checkpoint_kind == 'failure':
            self.execution_state.current_stage_index = int(
                payload.get('stage_index', self.execution_state.current_stage_index)
                or self.execution_state.current_stage_index
            )
            self.execution_state.current_increment = 0
        for state in self.partition_states:
            u_key = f'partition_{state.partition_id}_u'
            du_key = f'partition_{state.partition_id}_du'
            if u_key in arrays:
                state.u = np.asarray(arrays[u_key], dtype=float).copy()
            if du_key in arrays:
                state.du = np.asarray(arrays[du_key], dtype=float).copy()
            state.residual = np.zeros_like(np.asarray(state.u, dtype=float))

        self.result_store.restore_checkpoint_payload(
            dict(payload.get('result_store', {}) or {}),
            arrays=arrays,
        )
        self._hydrate_model_results_from_store(self._bundle.prepared_case.model)
        self.resume_checkpoint_id = checkpoint_id
        self.resume_checkpoint_selector = self.resume_checkpoint_selector or checkpoint_id
        self.resume_checkpoint_kind = checkpoint_kind
        self.resume_checkpoint_payload = payload
        self.resume_stage_reports = self._stage_reports_from_checkpoint(payload)
        self.result_store.metadata['resumed_from_checkpoint'] = checkpoint_id
        self.result_store.metadata['resume_checkpoint_selector'] = self.resume_checkpoint_selector
        self.result_store.metadata['resume_checkpoint_kind'] = checkpoint_kind
        self.result_store.metadata['resume_checkpoint_validation'] = dict(
            self.resume_checkpoint_validation or {}
        )
        if checkpoint_id not in self.checkpoint_manager.checkpoint_ids:
            self.checkpoint_manager.checkpoint_ids.append(checkpoint_id)
        self.telemetry.record_event(
            'runtime-resume',
            {
                'requested_checkpoint_id': self.resume_checkpoint_selector,
                'checkpoint_id': checkpoint_id,
                'checkpoint_kind': checkpoint_kind,
                'committed_stage_index': int(self.execution_state.committed_stage_index),
                'restart_stage_index': int(self.execution_state.current_stage_index),
            },
        )

    def _capture_stage_retry_state(self) -> dict[str, Any]:
        result_store_payload, result_store_arrays = self.result_store.export_checkpoint_payload()
        return {
            'backend_arrays': {
                str(name): np.asarray(values).copy()
                for name, values in self._runtime_arrays().items()
            },
            'backend_resume_state': dict(self._runtime_resume_payload()),
            'partition_states': [
                {
                    'partition_id': int(state.partition_id),
                    'u': np.asarray(state.u, dtype=float).copy(),
                    'du': np.asarray(state.du, dtype=float).copy(),
                    'residual': np.asarray(state.residual, dtype=float).copy(),
                    'metadata': dict(state.metadata),
                }
                for state in self.partition_states
            ],
            'result_store': result_store_payload,
            'result_store_arrays': {
                str(name): np.asarray(values).copy()
                for name, values in result_store_arrays.items()
            },
            'execution_state': {
                'current_stage_index': int(self.execution_state.current_stage_index),
                'current_increment': int(self.execution_state.current_increment),
                'committed_stage_index': int(self.execution_state.committed_stage_index),
                'committed_increment': int(self.execution_state.committed_increment),
                'wallclock_seconds': float(self.execution_state.wallclock_seconds),
                'last_checkpoint_id': self.execution_state.last_checkpoint_id,
                'metadata': dict(self.execution_state.metadata),
            },
            'last_reduction_summary': dict(self.last_reduction_summary),
            'model_metadata': copy.deepcopy(dict(self._bundle.prepared_case.model.metadata)),
        }

    def _restore_stage_retry_state(self, snapshot: dict[str, Any]) -> None:
        if self.backend_state is not None:
            self.local_backend.restore_runtime_state(
                self.backend_state,
                arrays=dict(snapshot.get('backend_arrays', {}) or {}),
                payload={
                    **dict(snapshot.get('backend_resume_state', {}) or {}),
                    'resume_mode': 'restore-checkpoint',
                },
            )
        for state, saved in zip(self.partition_states, list(snapshot.get('partition_states', []) or [])):
            state.u = np.asarray(saved.get('u', state.u), dtype=float).copy()
            state.du = np.asarray(saved.get('du', state.du), dtype=float).copy()
            state.residual = np.asarray(saved.get('residual', state.residual), dtype=float).copy()
            state.metadata = dict(saved.get('metadata', state.metadata))
        execution_state = dict(snapshot.get('execution_state', {}) or {})
        self.execution_state.current_stage_index = int(execution_state.get('current_stage_index', 0) or 0)
        self.execution_state.current_increment = int(execution_state.get('current_increment', 0) or 0)
        self.execution_state.committed_stage_index = int(execution_state.get('committed_stage_index', -1) or -1)
        self.execution_state.committed_increment = int(execution_state.get('committed_increment', -1) or -1)
        self.execution_state.wallclock_seconds = float(execution_state.get('wallclock_seconds', 0.0) or 0.0)
        self.execution_state.last_checkpoint_id = execution_state.get('last_checkpoint_id')
        self.execution_state.metadata = dict(execution_state.get('metadata', {}) or {})
        self.last_reduction_summary = dict(snapshot.get('last_reduction_summary', {}) or {})
        self.result_store.restore_checkpoint_payload(
            dict(snapshot.get('result_store', {}) or {}),
            arrays=dict(snapshot.get('result_store_arrays', {}) or {}),
        )
        self._bundle.prepared_case.model.metadata = copy.deepcopy(dict(snapshot.get('model_metadata', {}) or {}))
        self._hydrate_model_results_from_store(self._bundle.prepared_case.model)

    def _partition_diagnostics(self) -> list[dict[str, object]]:
        diagnostics: list[dict[str, object]] = []
        for state in self.partition_states:
            u = np.asarray(state.u, dtype=float)
            du = np.asarray(state.du, dtype=float)
            diagnostics.append(
                {
                    'partition_id': int(state.partition_id),
                    'u_norm': float(np.linalg.norm(u.reshape(-1))) if u.size else 0.0,
                    'du_norm': float(np.linalg.norm(du.reshape(-1))) if du.size else 0.0,
                    'neighbor_count': int(state.metadata.get('neighbor_count', 0) or 0),
                    'ghost_node_count': int(state.metadata.get('ghost_node_count', 0) or 0),
                }
            )
        return diagnostics

    def _partition_layout_summary(self) -> list[dict[str, object]]:
        if self._bundle is None:
            return []
        numbering = self._bundle.partitioned_model.numbering
        estimate_rows = list(
            self._bundle.compile_report.metadata.get('linear_system_partition_estimates', []) or []
        )
        estimate_by_partition = {
            int(item.get('partition_id', index)): dict(item)
            for index, item in enumerate(estimate_rows)
        }
        rows: list[dict[str, object]] = []
        for index, partition in enumerate(self._bundle.partitioned_model.partitions):
            partition_id = int(partition.partition_id)
            owned_dof_count = int(np.asarray(numbering.owned_dof_ids[index], dtype=np.int64).size)
            ghost_dof_count = int(np.asarray(numbering.ghost_dof_ids[index], dtype=np.int64).size)
            rows.append(
                {
                    'partition_id': partition_id,
                    'owned_cell_count': int(np.asarray(partition.owned_cell_ids, dtype=np.int64).size),
                    'owned_node_count': int(np.asarray(partition.owned_node_ids, dtype=np.int64).size),
                    'ghost_node_count': int(np.asarray(partition.ghost_node_ids, dtype=np.int64).size),
                    'neighbor_partition_ids': [int(item) for item in partition.neighbor_partition_ids],
                    'neighbor_count': int(len(partition.neighbor_partition_ids)),
                    'owned_dof_count': int(owned_dof_count),
                    'ghost_dof_count': int(ghost_dof_count),
                    'local_dof_count': int(owned_dof_count + ghost_dof_count),
                    'linear_system_estimate': dict(estimate_by_partition.get(partition_id, {})),
                }
            )
        return rows

    def _partition_node_maps(self) -> list[dict[str, object]]:
        if self._bundle is None:
            return []
        numbering = self._bundle.partitioned_model.numbering
        rows: list[dict[str, object]] = []
        for index, partition in enumerate(self._bundle.partitioned_model.partitions):
            rows.append(
                {
                    'partition_id': int(partition.partition_id),
                    'local_to_global_node': [
                        int(item)
                        for item in np.asarray(
                            numbering.local_to_global_node[index],
                            dtype=np.int64,
                        ).reshape(-1).tolist()
                    ],
                    'owned_node_ids': [
                        int(item)
                        for item in np.asarray(partition.owned_node_ids, dtype=np.int64).reshape(-1).tolist()
                    ],
                    'ghost_node_ids': [
                        int(item)
                        for item in np.asarray(partition.ghost_node_ids, dtype=np.int64).reshape(-1).tolist()
                    ],
                    'owned_node_count': int(
                        np.asarray(partition.owned_node_ids, dtype=np.int64).size
                    ),
                    'ghost_node_count': int(
                        np.asarray(partition.ghost_node_ids, dtype=np.int64).size
                    ),
                }
            )
        return rows

    def _linear_system_diagnostics_summary(self) -> dict[str, object]:
        stage_assets = [dict(item) for item in getattr(self.result_store, 'stage_assets', []) or []]
        diagnostics_rows = [
            dict(item.get('linear_system_diagnostics', {}) or {})
            for item in stage_assets
            if item.get('linear_system_diagnostics')
        ]
        if not diagnostics_rows:
            return {}
        stage_names = [str(item.get('stage_name')) for item in diagnostics_rows if item.get('stage_name')]
        stage_names_with_actual_operator = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if bool(item.get('has_actual_operator_summary', False)) and item.get('stage_name')
        ]
        stage_names_missing_actual_operator = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if not bool(item.get('has_actual_operator_summary', False)) and item.get('stage_name')
        ]
        active_cell_mismatch_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if item.get('active_cell_count_match') is False and item.get('stage_name')
        ]
        active_partition_mismatch_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if item.get('active_partition_count_match') is False and item.get('stage_name')
        ]
        ok_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if bool(item.get('ok', False)) and item.get('stage_name')
        ]
        issue_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if list(item.get('issues', []) or []) and item.get('stage_name')
        ]
        warning_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if list(item.get('warnings', []) or []) and item.get('stage_name')
        ]
        estimated_partition_only_stage_names = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if int(item.get('estimated_partition_local_system_count', 0) or 0) > 0
            and int(item.get('actual_partition_local_system_count', 0) or 0) == 0
            and item.get('stage_name')
        ]
        stages_with_actual_partition_local_systems = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if int(item.get('actual_partition_local_system_count', 0) or 0) > 0
            and item.get('stage_name')
        ]
        stage_names_with_actual_rhs_summary = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if int(item.get('actual_global_rhs_size', 0) or 0) > 0
            and item.get('stage_name')
        ]
        stage_names_with_partition_rhs_summary = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if int(item.get('actual_partition_rhs_size_total', 0) or 0) > 0
            and item.get('stage_name')
        ]
        stage_names_with_residual_summary = [
            str(item.get('stage_name'))
            for item in diagnostics_rows
            if int(item.get('actual_global_residual_size', 0) or 0) > 0
            and item.get('stage_name')
        ]
        consistency_levels = sorted(
            {
                str(item.get('consistency_level', 'unknown'))
                for item in diagnostics_rows
            }
        )
        return {
            'ok': bool(not issue_stage_names),
            'stage_count': int(len(diagnostics_rows)),
            'stage_names': stage_names,
            'stage_names_with_actual_operator': stage_names_with_actual_operator,
            'stage_names_missing_actual_operator': stage_names_missing_actual_operator,
            'stage_names_with_partition_rows': [
                str(item.get('stage_name'))
                for item in diagnostics_rows
                if int(item.get('actual_partition_row_count', 0) or 0) > 0 and item.get('stage_name')
            ],
            'ok_stage_names': ok_stage_names,
            'issue_stage_names': issue_stage_names,
            'warning_stage_names': warning_stage_names,
            'estimated_partition_only_stage_names': estimated_partition_only_stage_names,
            'stages_with_actual_partition_local_systems': stages_with_actual_partition_local_systems,
            'stage_names_with_actual_rhs_summary': stage_names_with_actual_rhs_summary,
            'stage_names_with_partition_rhs_summary': stage_names_with_partition_rhs_summary,
            'stage_names_with_residual_summary': stage_names_with_residual_summary,
            'consistency_levels': consistency_levels,
            'stages_with_actual_operator_count': int(len(stage_names_with_actual_operator)),
            'stages_missing_actual_operator_count': int(len(stage_names_missing_actual_operator)),
            'stages_with_actual_partition_local_systems_count': int(
                len(stages_with_actual_partition_local_systems)
            ),
            'stages_with_actual_rhs_summary_count': int(len(stage_names_with_actual_rhs_summary)),
            'stages_with_partition_rhs_summary_count': int(len(stage_names_with_partition_rhs_summary)),
            'stages_with_residual_summary_count': int(len(stage_names_with_residual_summary)),
            'stages_with_estimated_partition_only_count': int(
                len(estimated_partition_only_stage_names)
            ),
            'issue_count': int(
                sum(len(list(item.get('issues', []) or [])) for item in diagnostics_rows)
            ),
            'warning_count': int(
                sum(len(list(item.get('warnings', []) or [])) for item in diagnostics_rows)
            ),
            'active_cell_mismatch_stage_names': active_cell_mismatch_stage_names,
            'active_partition_mismatch_stage_names': active_partition_mismatch_stage_names,
            'planned_estimated_matrix_storage_bytes_total': int(
                sum(int(item.get('planned_estimated_matrix_storage_bytes', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_matrix_storage_bytes_total': int(
                sum(int(item.get('actual_matrix_storage_bytes', 0) or 0) for item in diagnostics_rows)
            ),
            'planned_estimated_active_local_dof_total': int(
                sum(int(item.get('planned_estimated_active_local_dof_total', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_global_dof_total': int(
                sum(int(item.get('actual_global_dof_count', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_global_rhs_size_total': int(
                sum(int(item.get('actual_global_rhs_size', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_global_rhs_norm_sum': float(
                sum(float(item.get('actual_global_rhs_norm', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_global_residual_norm_sum': float(
                sum(float(item.get('actual_global_residual_norm', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_global_reaction_norm_sum': float(
                sum(float(item.get('actual_global_reaction_norm', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_global_solution_size_total': int(
                sum(int(item.get('actual_solution_size', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_global_solution_norm_sum': float(
                sum(float(item.get('actual_solution_norm', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_partition_rhs_size_total': int(
                sum(int(item.get('actual_partition_rhs_size_total', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_partition_rhs_norm_sum': float(
                sum(float(item.get('actual_partition_rhs_norm_sum', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_partition_residual_norm_sum': float(
                sum(float(item.get('actual_partition_residual_norm_sum', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_partition_reaction_norm_sum': float(
                sum(float(item.get('actual_partition_reaction_norm_sum', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_partition_solution_norm_sum': float(
                sum(float(item.get('actual_partition_solution_norm_sum', 0.0) or 0.0) for item in diagnostics_rows)
            ),
            'actual_partition_fixed_local_dof_total': int(
                sum(int(item.get('actual_partition_fixed_local_dof_total', 0) or 0) for item in diagnostics_rows)
            ),
            'actual_partition_free_local_dof_total': int(
                sum(int(item.get('actual_partition_free_local_dof_total', 0) or 0) for item in diagnostics_rows)
            ),
        }

    def _record_global_reduction(
        self,
        *,
        stage_index: int,
        increment_index: int,
        global_residual: np.ndarray | None = None,
        global_reaction: np.ndarray | None = None,
    ) -> dict[str, object]:
        correction_local = 0.0
        displacement_local = 0.0
        max_abs_local = 0.0
        active_local = 0
        for state in self.partition_states:
            du = np.asarray(state.du, dtype=float).reshape(-1)
            u = np.asarray(state.u, dtype=float).reshape(-1)
            correction_local += float(np.dot(du, du)) if du.size else 0.0
            displacement_local += float(np.dot(u, u)) if u.size else 0.0
            if u.size:
                max_abs_local = max(max_abs_local, float(np.max(np.abs(u))))
                active_local += 1
        correction_norm = float(np.sqrt(self.communicator.allreduce_sum(correction_local)))
        displacement_norm = float(np.sqrt(self.communicator.allreduce_sum(displacement_local)))
        max_abs_u = float(self.communicator.allreduce_max(max_abs_local))
        active_partitions = int(self.communicator.allreduce_sum(active_local))
        residual_array = np.asarray(global_residual, dtype=float).reshape(-1) if global_residual is not None else np.empty((0,), dtype=float)
        reaction_array = np.asarray(global_reaction, dtype=float).reshape(-1) if global_reaction is not None else np.empty((0,), dtype=float)
        summary = {
            'stage_index': int(stage_index),
            'increment_index': int(increment_index),
            'correction_norm': correction_norm,
            'displacement_norm': displacement_norm,
            'max_abs_u': max_abs_u,
            'active_partitions': active_partitions,
            'residual_norm': float(np.linalg.norm(residual_array)) if residual_array.size else 0.0,
            'reaction_norm': float(np.linalg.norm(reaction_array)) if reaction_array.size else 0.0,
            'max_abs_residual': float(np.max(np.abs(residual_array))) if residual_array.size else 0.0,
            'max_abs_reaction': float(np.max(np.abs(reaction_array))) if reaction_array.size else 0.0,
        }
        self.last_reduction_summary = summary
        for state in self.partition_states:
            state.metadata['last_reduction_summary'] = dict(summary)
        self.telemetry.record_event('global-reduction', dict(summary))
        return summary

    def synchronize_partitions(self, *, stage_index: int, increment_index: int) -> dict[str, int]:
        if self._bundle is None:
            return {'exchange_count': 0, 'halo_node_count': 0}
        arrays = self._runtime_arrays()
        total_u = np.asarray(arrays.get('total_u', np.empty((0, 0), dtype=float)))
        residual = np.asarray(arrays.get('residual', np.empty((0, 0), dtype=float)))
        reaction = np.asarray(arrays.get('reaction', np.empty((0, 0), dtype=float)))
        if total_u.ndim != 2:
            return {'exchange_count': 0, 'halo_node_count': 0}

        numbering = self._bundle.partitioned_model.numbering
        halo_plans = self._bundle.partitioned_model.halo_plans
        exchange_count = 0
        halo_node_count = 0

        for index, partition_state in enumerate(self.partition_states):
            local_nodes = np.asarray(numbering.local_to_global_node[index], dtype=np.int64)
            local_u = (
                np.asarray(total_u[local_nodes], dtype=float)
                if local_nodes.size
                else np.empty((0, total_u.shape[1]), dtype=float)
            )
            previous = np.asarray(partition_state.u, dtype=float)
            partition_state.du = (
                local_u - previous
                if previous.shape == local_u.shape
                else np.zeros_like(local_u)
            )
            partition_state.u = local_u.copy()
            local_residual = (
                np.asarray(residual[local_nodes], dtype=float)
                if residual.ndim == 2 and residual.shape == total_u.shape and local_nodes.size
                else np.zeros_like(local_u)
            )
            partition_state.residual = local_residual.copy()
            if reaction.ndim == 2 and reaction.shape == total_u.shape and local_nodes.size:
                local_reaction = np.asarray(reaction[local_nodes], dtype=float)
                partition_state.metadata['local_reaction_norm'] = float(np.linalg.norm(local_reaction.reshape(-1)))
                partition_state.metadata['local_reaction_max_abs'] = (
                    float(np.max(np.abs(local_reaction.reshape(-1))))
                    if local_reaction.size
                    else 0.0
                )
            else:
                partition_state.metadata['local_reaction_norm'] = 0.0
                partition_state.metadata['local_reaction_max_abs'] = 0.0

            if index >= len(halo_plans):
                continue
            plan = halo_plans[index]
            send_buffers: dict[str, object] = {}
            for neighbor, send_nodes in zip(plan.send_neighbors, plan.send_node_ids):
                send_node_ids = np.asarray(send_nodes, dtype=np.int64)
                if send_node_ids.size == 0:
                    continue
                send_buffers[f'u:{neighbor}'] = np.asarray(total_u[send_node_ids], dtype=float).copy()
            if send_buffers:
                recv = self.communicator.exchange(plan, send_buffers)
                partition_state.metadata['last_exchange_keys'] = sorted(str(key) for key in recv.keys())
            exchange_count += len(send_buffers)
            halo_node_count += int(plan.metadata.get('halo_node_count', 0))

        if exchange_count or halo_node_count:
            self.telemetry.record_event(
                'halo-exchange',
                {
                    'stage_index': int(stage_index),
                    'increment_index': int(increment_index),
                    'exchange_count': int(exchange_count),
                    'halo_node_count': int(halo_node_count),
                },
            )
        reduction_summary = self._record_global_reduction(
            stage_index=stage_index,
            increment_index=increment_index,
            global_residual=(
                residual
                if residual.ndim == 2 and residual.shape == total_u.shape
                else None
            ),
            global_reaction=(
                reaction
                if reaction.ndim == 2 and reaction.shape == total_u.shape
                else None
            ),
        )
        return {
            'exchange_count': int(exchange_count),
            'halo_node_count': int(halo_node_count),
            'active_partitions': int(reduction_summary['active_partitions']),
        }

    def snapshot_state(
        self,
        *,
        stage_index: int | None = None,
        increment_index: int | None = None,
        include_arrays: bool = False,
    ) -> dict[str, Any]:
        partition_layout_metadata = []
        numbering_metadata = []
        stage_activation_state = []
        if self._bundle is not None:
            partition_layout_metadata = self._partition_layout_summary()
            for partition_index, partition in enumerate(self._bundle.partitioned_model.partitions):
                numbering_metadata.append(
                    {
                        'partition_id': int(partition.partition_id),
                        'owned_dof_range': list(
                            self._bundle.partitioned_model.numbering.owned_dof_ranges[partition_index]
                        ),
                        'owned_dof_count': int(
                            np.asarray(self._bundle.partitioned_model.numbering.owned_dof_ids[partition_index]).size
                        ),
                        'ghost_dof_count': int(
                            np.asarray(self._bundle.partitioned_model.numbering.ghost_dof_ids[partition_index]).size
                        ),
                    }
                )
            stage_plan = self._bundle.runtime_model.stage_plan
            for stage_offset, stage_name in enumerate(stage_plan.stage_names):
                activation_mask = stage_plan.activation_masks[stage_offset]
                stage_activation_state.append(
                    {
                        'stage_index': int(stage_offset),
                        'stage_name': str(stage_name),
                        'active_region_names': list(activation_mask.metadata.get('active_region_names', []) or []),
                        'active_cell_count': int(np.count_nonzero(np.asarray(activation_mask.active_cell_mask, dtype=bool))),
                    }
                )
        failure_policy = self.stage_executor.nonlinear_controller.failure_policy
        solver_policy = self.stage_executor.nonlinear_controller.solver_policy
        snapshot = {
            'runtime_schema_version': 3,
            'case_name': None if self._bundle is None else self._bundle.prepared_case.model.name,
            'partition_count': 0 if self._bundle is None else len(self._bundle.partitioned_model.partitions),
            'stage_index': None if stage_index is None else int(stage_index),
            'increment_index': None if increment_index is None else int(increment_index),
            'runtime_config': {
                'backend': str(self.config.backend),
                'communicator_backend': str(self.config.communicator_backend),
                'device_mode': str(self.config.device_mode),
                'partition_count': int(self.config.partition_count),
                'checkpoint_policy': str(self.config.checkpoint_policy),
                'telemetry_level': str(self.config.telemetry_level),
                'fail_policy': str(self.config.fail_policy),
                'deterministic': bool(self.config.deterministic),
            },
            'execution_state': {
                'current_stage_index': int(self.execution_state.current_stage_index),
                'current_increment': int(self.execution_state.current_increment),
                'committed_stage_index': int(self.execution_state.committed_stage_index),
                'committed_increment': int(self.execution_state.committed_increment),
                'wallclock_seconds': float(self.execution_state.wallclock_seconds),
                'last_checkpoint_id': self.execution_state.last_checkpoint_id,
            },
            'failure_policy': {
                'rollback_to_stage_start': bool(failure_policy.rollback_to_stage_start),
                'max_stage_retries': int(failure_policy.max_stage_retries),
                'max_increment_cutbacks': int(failure_policy.max_increment_cutbacks),
                'write_failure_checkpoint': bool(failure_policy.write_failure_checkpoint),
            },
            'solver_policy': {
                'nonlinear_max_iterations': int(solver_policy.nonlinear_max_iterations),
                'tolerance': float(solver_policy.tolerance),
                'line_search': bool(solver_policy.line_search),
                'max_cutbacks': int(solver_policy.max_cutbacks),
                'preconditioner': str(solver_policy.preconditioner),
                'solver_strategy': str(solver_policy.solver_strategy),
            },
            'telemetry_summary': self.telemetry.final_summary(),
            'result_store_summary': {
                'stage_count': len(self.result_store.stage_summaries),
                'field_count': len(self.result_store.field_snapshots),
                'stage_asset_count': len(self.result_store.stage_assets),
                'stage_linear_system_diagnostics_count': int(
                    sum(1 for item in self.result_store.stage_assets if item.get('linear_system_diagnostics'))
                ),
            },
            'partition_layout_metadata': partition_layout_metadata,
            'numbering_metadata': numbering_metadata,
            'stage_activation_state': stage_activation_state,
            'partition_state_summary': [
                {
                    'partition_id': int(state.partition_id),
                    'u_shape': tuple(np.asarray(state.u).shape),
                    'du_shape': tuple(np.asarray(state.du).shape),
                    'metadata': dict(state.metadata),
                }
                for state in self.partition_states
            ],
            'last_reduction_summary': dict(self.last_reduction_summary),
            'bootstrap_summary': self._bootstrap_summary(),
        }
        if include_arrays:
            array_payloads = self._runtime_arrays()
            for state in self.partition_states:
                array_payloads[f'partition_{state.partition_id}_u'] = np.asarray(state.u, dtype=float)
                array_payloads[f'partition_{state.partition_id}_du'] = np.asarray(state.du, dtype=float)
            result_store_payload, result_store_arrays = self.result_store.export_checkpoint_payload()
            array_payloads.update(result_store_arrays)
            snapshot['result_store'] = result_store_payload
            snapshot['backend_resume_state'] = self._runtime_resume_payload()
            if array_payloads:
                snapshot['_array_payloads'] = array_payloads
        return snapshot

    def execute(self) -> RuntimeExecutionReport:
        if self._bundle is None:
            raise RuntimeError('Runtime has not been initialized with a compilation bundle.')
        started = perf_counter()
        self.telemetry.record_event(
            'runtime-start',
            {
                'partition_count': len(self._bundle.partitioned_model.partitions),
                'device_mode': self.config.device_mode,
                'execution_path': (
                    'stage-executor'
                    if self.stage_execution_supported
                    else 'full-model-backend'
                ),
            },
        )

        solved_model = self._bundle.prepared_case.model
        stage_reports = list(self.resume_stage_reports)
        full_model_executed = False
        start_stage_index = (
            max(
                0,
                int(self.execution_state.current_stage_index)
                if self.resume_checkpoint_kind == 'failure'
                else int(self.execution_state.committed_stage_index) + 1,
            )
            if self.resume_checkpoint_id is not None
            else 0
        )

        if not self.stage_execution_supported:
            solved_model = self.local_backend.solve(
                self._bundle.prepared_case.model,
                self.solver_settings,
            )
            full_model_executed = True

        failure_policy = self.stage_executor.nonlinear_controller.failure_policy
        stage_retry_counts: dict[str, int] = {}
        retry_exhausted_stage_names: list[str] = []
        compiled_stage_partition_diagnostics = list(
            self._bundle.compile_report.metadata.get('stage_partition_diagnostics', []) or []
        )
        for stage_index in range(start_stage_index, len(self._bundle.runtime_model.stage_plan.stage_names)):
            stage_name = self._bundle.runtime_model.stage_plan.stage_names[stage_index]
            stage_obj = self._bundle.prepared_case.model.stage_by_name(stage_name)
            if stage_obj is None:
                stage_obj = AnalysisStage(name=stage_name)
            stage_retry_snapshot = self._capture_stage_retry_state() if self.stage_execution_supported else None
            stage_retry_count = 0
            stage_partition_activity = (
                dict(compiled_stage_partition_diagnostics[stage_index])
                if stage_index < len(compiled_stage_partition_diagnostics)
                else {}
            )
            while True:
                self.execution_state.current_stage_index = int(stage_index)
                context = RuntimeStageContext(
                    stage_index=stage_index,
                    stage_name=stage_name,
                    activation_mask=self._bundle.runtime_model.stage_plan.activation_masks[stage_index],
                    bc_table=self._bundle.runtime_model.stage_plan.bc_tables[stage_index],
                    load_table=self._bundle.runtime_model.stage_plan.load_tables[stage_index],
                    structure_mask=self._bundle.runtime_model.stage_plan.structure_masks[stage_index],
                    interface_mask=self._bundle.runtime_model.stage_plan.interface_masks[stage_index],
                    increment_plan=self.stage_executor.nonlinear_controller.increment_plan_for(stage_obj),
                    metadata={
                        'topo_order_index': stage_index,
                        'stage_attempt_count': int(stage_retry_count + 1),
                        'stage_retry_count': int(stage_retry_count),
                        'max_stage_retries': int(failure_policy.max_stage_retries),
                        'partition_activity': dict(stage_partition_activity),
                        'stage_linear_system_plan': (
                            dict(
                                self._bundle.compile_report.metadata.get('stage_linear_system_plans', [])[stage_index]
                            )
                            if stage_index < len(self._bundle.compile_report.metadata.get('stage_linear_system_plans', []) or [])
                            else {}
                        ),
                        'partition_layout': self._partition_layout_summary(),
                        'partition_node_maps': self._partition_node_maps(),
                        'linear_system_partition_estimates': list(
                            self._bundle.compile_report.metadata.get('linear_system_partition_estimates', []) or []
                        ),
                        **dict(stage_obj.metadata or {}),
                    },
                )
                stage_report = self.stage_executor.run_stage(stage_index, context, solved_model, self)
                stage_report.metadata['stage_retry_count'] = int(stage_retry_count)
                stage_report.metadata['stage_attempt_count'] = int(stage_retry_count + 1)
                if stage_report.ok:
                    break
                can_retry_stage = (
                    self.stage_execution_supported
                    and stage_retry_snapshot is not None
                    and failure_policy.rollback_to_stage_start
                    and stage_retry_count < int(failure_policy.max_stage_retries)
                )
                if not can_retry_stage:
                    if stage_retry_count > 0:
                        retry_exhausted_stage_names.append(stage_name)
                    break
                stage_retry_count += 1
                self.telemetry.record_event(
                    'stage-retry',
                    {
                        'stage_index': int(stage_index),
                        'stage_name': stage_name,
                        'retry_count': int(stage_retry_count),
                        'max_stage_retries': int(failure_policy.max_stage_retries),
                        'failure_checkpoint_id': stage_report.checkpoint_id,
                    },
                )
                self._restore_stage_retry_state(stage_retry_snapshot)
            stage_retry_counts[stage_name] = int(stage_retry_count)
            stage_reports.append(stage_report)
            if stage_report.ok:
                self.execution_state.committed_stage_index = int(stage_index)
                self.execution_state.current_increment = int(stage_report.increment_count)
                self.execution_state.committed_increment = int(stage_report.increment_count)
                if stage_report.checkpoint_id is not None:
                    self.execution_state.last_checkpoint_id = stage_report.checkpoint_id
            else:
                break

        if self.stage_execution_supported:
            solved_model = self.local_backend.finalize_runtime_state(
                solved_model,
                self.solver_settings,
                self.backend_state,
            )
        self.solved_model = solved_model

        runtime_seconds = float(perf_counter() - started)
        self.execution_state.wallclock_seconds = runtime_seconds
        self.telemetry.record_event(
            'runtime-complete',
            {
                'runtime_seconds': runtime_seconds,
                'stage_count': len(stage_reports),
            },
        )
        telemetry_summary = self.telemetry.final_summary()
        executed_stage_names = tuple(solved_model.metadata.get('stages_run', []) or ())
        expected_stage_names = tuple(self._bundle.runtime_model.stage_plan.stage_names)
        stage_reports_ok = all(report.ok for report in stage_reports)
        ok = stage_reports_ok and (
            executed_stage_names == expected_stage_names
            or (
                not executed_stage_names
                and len(expected_stage_names) == 1
                and expected_stage_names[0] == 'default'
            )
        )
        execution_mode = (
            'stage-executor'
            if self.stage_execution_supported
            else 'local-full-model-backend'
        )
        partition_diagnostics = self._partition_diagnostics()
        bootstrap_summary = self._bootstrap_summary()
        checkpoint_ids = tuple(
            self.checkpoint_manager.list_checkpoint_ids()
            if self.checkpoint_manager is not None
            else ()
        )
        stage_checkpoint_ids = tuple(
            checkpoint_id
            for checkpoint_id in checkpoint_ids
            if str(checkpoint_id).startswith('stage-')
        )
        failure_checkpoint_ids = tuple(
            checkpoint_id
            for checkpoint_id in checkpoint_ids
            if str(checkpoint_id).startswith('failure-')
        )
        self.result_store.metadata['execution_mode'] = execution_mode
        self.result_store.metadata['full_model_executed'] = bool(full_model_executed)
        self.result_store.metadata['partition_diagnostics'] = partition_diagnostics
        self.result_store.metadata['stage_partition_diagnostics'] = list(
            self._bundle.compile_report.metadata.get('stage_partition_diagnostics', []) or []
        )
        self.result_store.metadata['stage_linear_system_plans'] = list(
            self._bundle.compile_report.metadata.get('stage_linear_system_plans', []) or []
        )
        self.result_store.metadata['linear_system_partition_estimates'] = list(
            self._bundle.compile_report.metadata.get('linear_system_partition_estimates', []) or []
        )
        self.result_store.metadata['partition_advisory'] = dict(
            self._bundle.compile_report.metadata.get('partition_advisory', {}) or {}
        )
        self.result_store.metadata['stage_execution_diagnostics'] = dict(self.stage_execution_diagnostics)
        self.result_store.metadata['bootstrap_summary'] = bootstrap_summary
        self.result_store.metadata['stage_checkpoint_ids'] = list(stage_checkpoint_ids)
        self.result_store.metadata['increment_checkpoint_ids'] = [
            checkpoint_id
            for checkpoint_id in checkpoint_ids
            if str(checkpoint_id).startswith('increment-')
        ]
        self.result_store.metadata['failure_checkpoint_ids'] = list(failure_checkpoint_ids)
        self.result_store.metadata['checkpoint_policy'] = (
            {}
            if self.checkpoint_manager is None
            else {
                'save_at_stage_end': bool(self.checkpoint_manager.policy.save_at_stage_end),
                'save_at_failure': bool(self.checkpoint_manager.policy.save_at_failure),
                'save_every_n_increments': int(self.checkpoint_manager.policy.save_every_n_increments),
                'keep_last_n': int(self.checkpoint_manager.policy.keep_last_n),
            }
        )
        self.result_store.metadata['failure_policy'] = {
            'rollback_to_stage_start': bool(failure_policy.rollback_to_stage_start),
            'max_stage_retries': int(failure_policy.max_stage_retries),
            'max_increment_cutbacks': int(failure_policy.max_increment_cutbacks),
        }
        self.result_store.metadata['checkpoint_dir'] = (
            None
            if self.checkpoint_manager is None
            else str(self.checkpoint_manager.base_dir)
        )
        self.result_store.metadata['stage_retry_counts'] = dict(stage_retry_counts)
        self.result_store.metadata['total_stage_retry_count'] = int(sum(stage_retry_counts.values()))
        self.result_store.metadata['retry_exhausted_stage_names'] = list(retry_exhausted_stage_names)
        self.result_store.metadata['stage_asset_count'] = int(len(self.result_store.stage_assets))
        self.result_store.metadata['stage_linear_system_diagnostics_count'] = int(
            sum(1 for item in self.result_store.stage_assets if item.get('linear_system_diagnostics'))
        )
        linear_system_diagnostics_summary = self._linear_system_diagnostics_summary()
        self.result_store.metadata['linear_system_diagnostics_summary'] = dict(
            linear_system_diagnostics_summary
        )
        if self.resume_checkpoint_id is not None:
            self.result_store.metadata['resumed_from_checkpoint'] = self.resume_checkpoint_id
            self.result_store.metadata['resume_checkpoint_selector'] = self.resume_checkpoint_selector
            self.result_store.metadata['resume_checkpoint_kind'] = self.resume_checkpoint_kind
            self.result_store.metadata['resume_checkpoint_validation'] = dict(
                self.resume_checkpoint_validation or {}
            )
        return RuntimeExecutionReport(
            ok=ok,
            stage_reports=tuple(stage_reports),
            telemetry_summary=telemetry_summary,
            checkpoints=checkpoint_ids,
            metadata={
                'execution_mode': execution_mode,
                'partition_count': len(self._bundle.partitioned_model.partitions),
                'executed_stage_names': executed_stage_names,
                'expected_stage_names': expected_stage_names,
                'stage_execution_supported': bool(self.stage_execution_supported),
                'resumed_from_checkpoint': self.resume_checkpoint_id,
                'resume_checkpoint_selector': self.resume_checkpoint_selector,
                'resume_checkpoint_kind': self.resume_checkpoint_kind,
                'restored_stage_count': len(self.resume_stage_reports),
                'last_reduction_summary': dict(self.last_reduction_summary),
                'partition_diagnostics': partition_diagnostics,
                'stage_partition_diagnostics': list(
                    self._bundle.compile_report.metadata.get('stage_partition_diagnostics', []) or []
                ),
                'stage_linear_system_plans': list(
                    self._bundle.compile_report.metadata.get('stage_linear_system_plans', []) or []
                ),
                'linear_system_partition_estimates': list(
                    self._bundle.compile_report.metadata.get('linear_system_partition_estimates', []) or []
                ),
                'stage_asset_count': int(len(self.result_store.stage_assets)),
                'stage_linear_system_diagnostics_count': int(
                    sum(1 for item in self.result_store.stage_assets if item.get('linear_system_diagnostics'))
                ),
                'stage_assets': [dict(item) for item in self.result_store.stage_assets],
                'linear_system_diagnostics_summary': dict(linear_system_diagnostics_summary),
                'partition_advisory': dict(
                    self._bundle.compile_report.metadata.get('partition_advisory', {}) or {}
                ),
                'stage_execution_diagnostics': dict(self.stage_execution_diagnostics),
                'bootstrap_summary': bootstrap_summary,
                'resolved_resume_checkpoint_id': self.resume_checkpoint_id,
                'resume_checkpoint_validation': dict(self.resume_checkpoint_validation or {}),
                'checkpoint_policy': (
                    {}
                    if self.checkpoint_manager is None
                    else {
                        'save_at_stage_end': bool(self.checkpoint_manager.policy.save_at_stage_end),
                        'save_at_failure': bool(self.checkpoint_manager.policy.save_at_failure),
                        'save_every_n_increments': int(self.checkpoint_manager.policy.save_every_n_increments),
                        'keep_last_n': int(self.checkpoint_manager.policy.keep_last_n),
                    }
                ),
                'checkpoint_dir': (
                    None
                    if self.checkpoint_manager is None
                    else str(self.checkpoint_manager.base_dir)
                ),
                'failure_policy': {
                    'rollback_to_stage_start': bool(failure_policy.rollback_to_stage_start),
                    'max_stage_retries': int(failure_policy.max_stage_retries),
                    'max_increment_cutbacks': int(failure_policy.max_increment_cutbacks),
                },
                'stage_retry_counts': dict(stage_retry_counts),
                'total_stage_retry_count': int(sum(stage_retry_counts.values())),
                'retry_exhausted_stage_names': tuple(retry_exhausted_stage_names),
                'stage_checkpoint_ids': stage_checkpoint_ids,
                'increment_checkpoint_ids': tuple(
                    checkpoint_id
                    for checkpoint_id in checkpoint_ids
                    if str(checkpoint_id).startswith('increment-')
                ),
                'failure_checkpoint_ids': failure_checkpoint_ids,
                'last_checkpoint_id': self.execution_state.last_checkpoint_id,
            },
        )

    def shutdown(self):
        self.communicator.barrier()
        self._bundle = None
