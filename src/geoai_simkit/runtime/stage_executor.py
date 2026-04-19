from __future__ import annotations

from time import perf_counter

import numpy as np

from .bundle import StageRunReport
from .errors import RecoverableIncrementError


class StageExecutor:
    def __init__(self, nonlinear_controller, checkpoint_manager, telemetry, result_store):
        self.nonlinear_controller = nonlinear_controller
        self.checkpoint_manager = checkpoint_manager
        self.telemetry = telemetry
        self.result_store = result_store

    @staticmethod
    def _normalized_shape(value) -> list[int]:
        shape = list(value or [])
        if len(shape) >= 2:
            return [int(shape[0] or 0), int(shape[1] or 0)]
        if len(shape) == 1:
            return [int(shape[0] or 0), int(shape[0] or 0)]
        return [0, 0]

    @staticmethod
    def _safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
        denom = float(denominator)
        if denom <= 0.0:
            return None
        return float(float(numerator) / denom)

    @staticmethod
    def _matrix_summary_from_operator_linear_system(
        linear_system: dict[str, object] | None,
    ) -> dict[str, object]:
        payload = dict(linear_system or {})
        matrix_summary = dict(payload.get('matrix', {}) or {})
        if matrix_summary:
            return matrix_summary
        return {
            key: value
            for key, value in payload.items()
            if key in {'shape', 'block_size', 'storage', 'nnz_entries', 'nnz_blocks', 'density', 'storage_bytes'}
        }

    @staticmethod
    def _compact_linear_system_diagnostics(
        diagnostics: dict[str, object] | None,
    ) -> dict[str, object]:
        row = dict(diagnostics or {})
        return {
            'has_actual_operator_summary': bool(row.get('has_actual_operator_summary', False)),
            'planned_estimated_matrix_storage_bytes': int(
                row.get('planned_estimated_matrix_storage_bytes', 0) or 0
            ),
            'actual_matrix_storage_bytes': int(
                row.get('actual_matrix_storage_bytes', 0) or 0
            ),
            'actual_global_dof_count': int(row.get('actual_global_dof_count', 0) or 0),
            'actual_global_rhs_size': int(row.get('actual_global_rhs_size', 0) or 0),
            'actual_global_residual_norm': float(row.get('actual_global_residual_norm', 0.0) or 0.0),
            'actual_global_reaction_norm': float(row.get('actual_global_reaction_norm', 0.0) or 0.0),
            'actual_partition_rhs_size_total': int(
                row.get('actual_partition_rhs_size_total', 0) or 0
            ),
            'actual_partition_residual_norm_sum': float(
                row.get('actual_partition_residual_norm_sum', 0.0) or 0.0
            ),
            'actual_partition_reaction_norm_sum': float(
                row.get('actual_partition_reaction_norm_sum', 0.0) or 0.0
            ),
            'active_cell_count_match': row.get('active_cell_count_match'),
            'active_partition_count_match': row.get('active_partition_count_match'),
            'consistency_level': str(row.get('consistency_level', 'estimated-only')),
            'ok': bool(row.get('ok', True)),
        }

    def _build_linear_system_diagnostics(
        self,
        *,
        stage_index: int,
        stage_name: str,
        execution_path: str,
        status: str,
        stage_summary: dict[str, object],
        stage_linear_system_plan: dict[str, object] | None,
        operator_summary: dict[str, object] | None,
        partition_linear_systems: list[dict[str, object]] | None,
    ) -> dict[str, object]:
        plan = dict(stage_linear_system_plan or {})
        operator = dict(operator_summary or {})
        actual_linear_system = dict(operator.get('linear_system', {}) or {})
        actual_matrix_summary = self._matrix_summary_from_operator_linear_system(actual_linear_system)
        planned_partition_rows = [dict(item) for item in plan.get('partition_local_systems', []) or []]
        actual_partition_rows = [dict(item) for item in partition_linear_systems or []]
        plan_by_partition = {
            int(item.get('partition_id', index)): dict(item)
            for index, item in enumerate(planned_partition_rows)
        }
        actual_by_partition = {
            int(item.get('partition_id', index)): dict(item)
            for index, item in enumerate(actual_partition_rows)
        }
        partition_ids = sorted(set(plan_by_partition.keys()) | set(actual_by_partition.keys()))
        partition_rows: list[dict[str, object]] = []
        partition_active_matches = 0
        partition_active_cell_matches = 0
        for partition_id in partition_ids:
            planned_row = dict(plan_by_partition.get(partition_id, {}) or {})
            actual_row = dict(actual_by_partition.get(partition_id, {}) or {})
            planned_present = bool(planned_row)
            actual_present = bool(actual_row)
            planned_active = None if not planned_present else bool(planned_row.get('active', False))
            actual_active = None if not actual_present else bool(actual_row.get('active', False))
            planned_active_cell_count = (
                None
                if not planned_present
                else int(planned_row.get('active_cell_count', 0) or 0)
            )
            actual_active_cell_count = (
                None
                if not actual_present
                else int(actual_row.get('active_cell_count', 0) or 0)
            )
            active_match = (
                None
                if planned_active is None or actual_active is None
                else bool(planned_active == actual_active)
            )
            active_cell_count_match = (
                None
                if planned_active_cell_count is None or actual_active_cell_count is None
                else bool(planned_active_cell_count == actual_active_cell_count)
            )
            if active_match is True:
                partition_active_matches += 1
            if active_cell_count_match is True:
                partition_active_cell_matches += 1
            partition_rows.append(
                {
                    'partition_id': int(partition_id),
                    'planned_present': planned_present,
                    'actual_present': actual_present,
                    'planned_active': planned_active,
                    'actual_active': actual_active,
                    'planned_active_cell_count': planned_active_cell_count,
                    'actual_active_cell_count': actual_active_cell_count,
                    'planned_estimated_local_dof_count': (
                        None
                        if not planned_present
                        else int(
                            planned_row.get(
                                'estimated_active_local_dof_count',
                                planned_row.get('active_owned_dof_count', 0),
                            )
                            or 0
                        )
                    ),
                    'actual_local_dof_count': (
                        None
                        if not actual_present
                        else int(
                            actual_row.get(
                                'local_dof_count',
                                actual_row.get('estimated_active_local_dof_count', 0),
                            )
                            or 0
                        )
                    ),
                    'planned_matrix_storage_bytes': (
                        None
                        if not planned_present
                        else int(planned_row.get('matrix_storage_bytes_estimate', 0) or 0)
                    ),
                    'actual_matrix_storage_bytes': (
                        None
                        if not actual_present
                        else int(
                            actual_row.get(
                                'matrix_storage_bytes',
                                actual_row.get('matrix_storage_bytes_estimate', 0),
                            )
                            or 0
                        )
                    ),
                    'actual_rhs_size': (
                        None
                        if not actual_present
                        else int(actual_row.get('rhs_size', 0) or 0)
                    ),
                    'actual_rhs_norm': (
                        None
                        if not actual_present
                        else float(actual_row.get('rhs_norm', 0.0) or 0.0)
                    ),
                    'actual_fixed_local_dof_count': (
                        None
                        if not actual_present
                        else int(actual_row.get('fixed_local_dof_count', 0) or 0)
                    ),
                    'actual_free_local_dof_count': (
                        None
                        if not actual_present
                        else int(actual_row.get('free_local_dof_count', 0) or 0)
                    ),
                    'actual_solution_norm': (
                        None
                        if not actual_present
                        else float(actual_row.get('solution_norm', 0.0) or 0.0)
                    ),
                    'active_match': active_match,
                    'active_cell_count_match': active_cell_count_match,
                }
            )
        partition_row_sources = sorted(
            {
                str(item.get('summary_source', 'unknown'))
                for item in actual_partition_rows
            }
        )
        actual_partition_local_system_count = int(
            sum(
                1
                for item in actual_partition_rows
                if bool(item.get('has_actual_local_matrix', False))
                or str(item.get('matrix_summary_kind', '')) == 'actual-local-partition'
            )
        )
        estimated_partition_local_system_count = int(
            max(0, len(actual_partition_rows) - actual_partition_local_system_count)
        )

        planned_active_partition_count = (
            None
            if not plan
            else int(plan.get('active_partition_count', 0) or 0)
        )
        actual_active_partition_count = (
            None
            if 'active_partition_count' not in stage_summary
            else int(stage_summary.get('active_partition_count', 0) or 0)
        )
        planned_active_cell_count = (
            None
            if not plan
            else int(plan.get('active_cell_count', 0) or 0)
        )
        actual_active_cell_count = int(stage_summary.get('active_cell_count', 0) or 0)
        actual_matrix_shape = self._normalized_shape(actual_matrix_summary.get('shape'))
        actual_global_dof_count = int(actual_matrix_shape[0])
        actual_matrix_storage_bytes = int(actual_matrix_summary.get('storage_bytes', 0) or 0)
        actual_global_rhs_size = int(actual_linear_system.get('rhs_size', 0) or 0)
        actual_global_rhs_norm = float(actual_linear_system.get('rhs_norm', 0.0) or 0.0)
        actual_global_residual_size = int(actual_linear_system.get('residual_size', 0) or 0)
        actual_global_residual_norm = float(actual_linear_system.get('residual_norm', 0.0) or 0.0)
        actual_global_reaction_size = int(actual_linear_system.get('reaction_size', 0) or 0)
        actual_global_reaction_norm = float(actual_linear_system.get('reaction_norm', 0.0) or 0.0)
        actual_fixed_dof_count = int(actual_linear_system.get('fixed_dof_count', 0) or 0)
        actual_free_dof_count = int(actual_linear_system.get('free_dof_count', 0) or 0)
        actual_solution_size = int(actual_linear_system.get('solution_size', 0) or 0)
        actual_solution_norm = float(actual_linear_system.get('solution_norm', 0.0) or 0.0)
        actual_partition_rhs_size_total = int(
            sum(int(item.get('rhs_size', 0) or 0) for item in actual_partition_rows)
        )
        actual_partition_rhs_norm_sum = float(
            sum(float(item.get('rhs_norm', 0.0) or 0.0) for item in actual_partition_rows)
        )
        actual_partition_residual_norm_sum = float(
            sum(float(item.get('residual_norm', 0.0) or 0.0) for item in actual_partition_rows)
        )
        actual_partition_reaction_norm_sum = float(
            sum(float(item.get('reaction_norm', 0.0) or 0.0) for item in actual_partition_rows)
        )
        actual_partition_solution_norm_sum = float(
            sum(float(item.get('solution_norm', 0.0) or 0.0) for item in actual_partition_rows)
        )
        actual_partition_fixed_local_dof_total = int(
            sum(int(item.get('fixed_local_dof_count', 0) or 0) for item in actual_partition_rows)
        )
        actual_partition_free_local_dof_total = int(
            sum(int(item.get('free_local_dof_count', 0) or 0) for item in actual_partition_rows)
        )
        planned_estimated_active_local_dof_total = int(
            plan.get('estimated_active_local_dof_total', 0) or 0
        )
        planned_estimated_matrix_storage_bytes = int(
            plan.get('estimated_matrix_storage_bytes', 0) or 0
        )
        global_plan_vs_actual_ok = all(
            value is not False
            for value in (
                None if planned_active_cell_count is None else bool(planned_active_cell_count == actual_active_cell_count),
                (
                    None
                    if planned_active_partition_count is None or actual_active_partition_count is None
                    else bool(planned_active_partition_count == actual_active_partition_count)
                ),
            )
        )
        issues: list[str] = []
        warnings: list[str] = []
        if not plan:
            warnings.append('stage_linear_system_plan is missing')
        if str(status) == 'completed' and not actual_linear_system:
            warnings.append('global operator linear system summary is missing')
        if bool(actual_linear_system) and actual_global_dof_count > 0 and actual_global_rhs_size == 0:
            warnings.append('global operator rhs summary is missing')
        if bool(actual_linear_system) and actual_global_dof_count > 0 and actual_global_residual_size == 0:
            warnings.append('global operator residual summary is missing')
        if planned_active_cell_count is not None and planned_active_cell_count != actual_active_cell_count:
            issues.append('planned_active_cell_count does not match stage summary active_cell_count')
        if (
            planned_active_partition_count is not None
            and actual_active_partition_count is not None
            and planned_active_partition_count != actual_active_partition_count
        ):
            issues.append(
                'planned_active_partition_count does not match stage summary active_partition_count'
            )
        if actual_partition_rows and actual_partition_local_system_count == 0:
            warnings.append('partition_local_systems are estimate-derived only')
        if not actual_partition_rows and str(status) == 'completed':
            warnings.append('partition_local_systems are missing')
        consistency_level = (
            'full'
            if bool(actual_linear_system) and actual_partition_local_system_count > 0 and not issues
            else (
                'global-actual-partition-estimated'
                if bool(actual_linear_system) and estimated_partition_local_system_count > 0 and not issues
                else (
                    'estimated-only'
                    if not bool(actual_linear_system)
                    else 'mismatch'
                )
            )
        )
        return {
            'stage_index': int(stage_index),
            'stage_name': str(stage_name),
            'execution_path': str(execution_path),
            'status': str(status),
            'has_stage_plan': bool(plan),
            'has_operator_summary': bool(operator),
            'has_actual_operator_summary': bool(actual_linear_system),
            'planned_active_partition_count': planned_active_partition_count,
            'actual_active_partition_count': actual_active_partition_count,
            'active_partition_count_match': (
                None
                if planned_active_partition_count is None or actual_active_partition_count is None
                else bool(planned_active_partition_count == actual_active_partition_count)
            ),
            'planned_active_cell_count': planned_active_cell_count,
            'actual_active_cell_count': int(actual_active_cell_count),
            'active_cell_count_match': (
                None
                if planned_active_cell_count is None
                else bool(planned_active_cell_count == actual_active_cell_count)
            ),
            'planned_partition_row_count': int(len(planned_partition_rows)),
            'actual_partition_row_count': int(len(actual_partition_rows)),
            'matched_partition_row_count': int(
                sum(1 for row in partition_rows if row['planned_present'] and row['actual_present'])
            ),
            'partition_row_sources': partition_row_sources,
            'actual_partition_local_system_count': int(actual_partition_local_system_count),
            'estimated_partition_local_system_count': int(estimated_partition_local_system_count),
            'partition_active_match_count': int(partition_active_matches),
            'partition_active_cell_match_count': int(partition_active_cell_matches),
            'planned_estimated_active_local_dof_total': int(planned_estimated_active_local_dof_total),
            'actual_global_dof_count': int(actual_global_dof_count),
            'actual_global_rhs_size': int(actual_global_rhs_size),
            'actual_global_rhs_norm': float(actual_global_rhs_norm),
            'actual_global_residual_size': int(actual_global_residual_size),
            'actual_global_residual_norm': float(actual_global_residual_norm),
            'actual_global_reaction_size': int(actual_global_reaction_size),
            'actual_global_reaction_norm': float(actual_global_reaction_norm),
            'actual_fixed_dof_count': int(actual_fixed_dof_count),
            'actual_free_dof_count': int(actual_free_dof_count),
            'actual_solution_size': int(actual_solution_size),
            'actual_solution_norm': float(actual_solution_norm),
            'actual_matrix_shape': list(actual_matrix_shape),
            'planned_estimated_matrix_storage_bytes': int(planned_estimated_matrix_storage_bytes),
            'actual_matrix_storage_bytes': int(actual_matrix_storage_bytes),
            'actual_partition_rhs_size_total': int(actual_partition_rhs_size_total),
            'actual_partition_rhs_norm_sum': float(actual_partition_rhs_norm_sum),
            'actual_partition_residual_norm_sum': float(actual_partition_residual_norm_sum),
            'actual_partition_reaction_norm_sum': float(actual_partition_reaction_norm_sum),
            'actual_partition_solution_norm_sum': float(actual_partition_solution_norm_sum),
            'actual_partition_fixed_local_dof_total': int(actual_partition_fixed_local_dof_total),
            'actual_partition_free_local_dof_total': int(actual_partition_free_local_dof_total),
            'matrix_storage_ratio_actual_to_estimated': self._safe_ratio(
                actual_matrix_storage_bytes,
                planned_estimated_matrix_storage_bytes,
            ),
            'global_dof_ratio_actual_to_estimated_local': self._safe_ratio(
                actual_global_dof_count,
                planned_estimated_active_local_dof_total,
            ),
            'global_plan_vs_actual_ok': bool(global_plan_vs_actual_ok),
            'consistency_level': str(consistency_level),
            'ok': bool(not issues),
            'issues': issues,
            'warnings': warnings,
            'partition_rows': partition_rows,
        }

    def _record_stage_summary(
        self,
        *,
        stage_index: int,
        context,
        fields,
        status: str,
        increment_count: int,
        iteration_count: int,
    ) -> dict[str, object]:
        summary = {
            'stage_index': int(stage_index),
            'stage_name': context.stage_name,
            'status': str(status),
            'active_cell_count': int(np.count_nonzero(context.activation_mask.active_cell_mask)),
            'active_region_count': int(len(np.asarray(context.activation_mask.active_region_codes).reshape(-1))),
            'increment_count': int(increment_count),
            'iteration_count': int(iteration_count),
            'field_names': [field.name for field in fields],
        }
        partition_activity = dict(context.metadata.get('partition_activity', {}) or {})
        if partition_activity:
            summary.update(
                {
                    'active_partition_count': int(partition_activity.get('active_partition_count', 0) or 0),
                    'stage_locality_ratio': float(partition_activity.get('stage_locality_ratio', 0.0) or 0.0),
                    'active_partition_balance_ratio': float(partition_activity.get('active_partition_balance_ratio', 1.0) or 1.0),
                    'active_node_balance_ratio': float(partition_activity.get('active_node_balance_ratio', 1.0) or 1.0),
                    'idle_partition_ids': list(partition_activity.get('idle_partition_ids', []) or []),
                    'active_cells_per_partition': list(partition_activity.get('active_cells_per_partition', []) or []),
                    'active_gp_states_per_partition': list(partition_activity.get('active_gp_states_per_partition', []) or []),
                    'active_owned_nodes_per_partition': list(partition_activity.get('active_owned_nodes_per_partition', []) or []),
                    'active_owned_dofs_per_partition': list(partition_activity.get('active_owned_dofs_per_partition', []) or []),
                }
            )
        return summary

    def _run_postprocessed_stage(self, stage_index, context, solved_model, runtime) -> StageRunReport:
        started = perf_counter()
        stage_name = context.stage_name
        fields = solved_model.results_for_stage(stage_name)
        executed_stages = tuple(solved_model.metadata.get('stages_run', []) or ())
        ok = stage_name in executed_stages or (not executed_stages and not solved_model.stages)
        solver_history = dict(solved_model.metadata.get('solver_history', {}) or {})
        step_trace = dict(solved_model.metadata.get('step_control_trace', {}) or {})
        stage_history = list(solver_history.get(stage_name, []) or [])
        stage_steps = list(step_trace.get(stage_name, []) or [])

        for field in fields:
            self.result_store.capture_field(field)

        for increment_index, row in enumerate(stage_history, start=1):
            self.result_store.increment_summaries.append(
                {
                    'stage_index': int(stage_index),
                    'stage_name': stage_name,
                    'increment_index': int(increment_index),
                    'payload': dict(row),
                }
            )

        stage_summary = self._record_stage_summary(
            stage_index=stage_index,
            context=context,
            fields=fields,
            status='completed' if ok else 'not-executed',
            increment_count=max(len(stage_steps), int(context.increment_plan.target_steps)),
            iteration_count=len(stage_history),
        )
        linear_system_diagnostics = self._build_linear_system_diagnostics(
            stage_index=stage_index,
            stage_name=stage_name,
            execution_path='postprocessed-full-model',
            status='completed' if ok else 'not-executed',
            stage_summary=stage_summary,
            stage_linear_system_plan=dict(context.metadata.get('stage_linear_system_plan', {}) or {}),
            operator_summary={},
            partition_linear_systems=[],
        )
        stage_summary['linear_system_diagnostics_summary'] = self._compact_linear_system_diagnostics(
            linear_system_diagnostics
        )
        self.result_store.stage_summaries.append(stage_summary)
        self.result_store.capture_stage_asset(
            {
                'stage_index': int(stage_index),
                'stage_name': stage_name,
                'execution_path': 'postprocessed-full-model',
                'status': 'completed' if ok else 'not-executed',
                'stage_summary': dict(stage_summary),
                'stage_linear_system_plan': dict(context.metadata.get('stage_linear_system_plan', {}) or {}),
                'linear_system_diagnostics': dict(linear_system_diagnostics),
            }
        )
        self.telemetry.record_event(
            'stage-summary',
            {
                **stage_summary,
                'duration_seconds': float(perf_counter() - started),
            },
        )

        checkpoint_id = None
        if self.checkpoint_manager is not None and self.checkpoint_manager.policy.save_at_stage_end:
            checkpoint_id = self.checkpoint_manager.save_stage_checkpoint(
                runtime,
                int(stage_index),
                payload={
                    **runtime.snapshot_state(stage_index=stage_index, include_arrays=True),
                    'stage_summary': stage_summary,
                },
            )

        return StageRunReport(
            stage_index=int(stage_index),
            stage_name=stage_name,
            ok=ok,
            status='completed' if ok else 'not-executed',
            active_cell_count=int(stage_summary['active_cell_count']),
            active_region_count=int(stage_summary['active_region_count']),
            increment_count=int(stage_summary['increment_count']),
            iteration_count=int(stage_summary['iteration_count']),
            field_names=tuple(field.name for field in fields),
            checkpoint_id=checkpoint_id,
            metadata={
                'history_rows': len(stage_history),
                'step_trace_rows': len(stage_steps),
                'execution_path': 'postprocessed-full-model',
                'linear_system_diagnostics': dict(linear_system_diagnostics),
            },
        )

    def _run_stage_execution(self, stage_index, context, solved_model, runtime) -> StageRunReport:
        started = perf_counter()
        stage_name = context.stage_name
        active_regions = tuple(context.activation_mask.metadata.get('active_region_names', []) or [])
        target_steps = max(1, int(context.increment_plan.target_steps))
        runtime.local_backend.begin_stage(runtime.backend_state, stage_name=stage_name)

        history_rows: list[dict[str, object]] = []
        step_trace_rows: list[dict[str, object]] = []
        increment_result = None
        checkpoint_id = None
        commit_info: dict[str, object] = {}
        ok = True
        status = 'completed'
        failure_error: str | None = None
        completed_steps = 0
        attempt_count = 0
        cutback_count = 0
        load_factor = 0.0
        max_cutbacks = max(0, int(context.increment_plan.metadata.get('max_cutbacks', 0) or 0))
        min_step_size = float(context.increment_plan.min_step_size)
        max_step_size = float(context.increment_plan.max_step_size)
        growth_factor = max(1.0, float(context.increment_plan.growth_factor or 1.0))
        shrink_factor = min(0.999, max(1.0e-6, float(context.increment_plan.shrink_factor or 1.0)))
        step_size = float(context.increment_plan.metadata.get('initial_step_size', 1.0 / float(target_steps)))
        step_size = min(max_step_size, max(min_step_size, step_size))

        def _capture_attempt_state() -> dict[str, object]:
            return {
                'backend_arrays': {
                    str(name): np.asarray(values, dtype=float).copy()
                    for name, values in runtime._runtime_arrays().items()
                },
                'backend_payload': dict(runtime._runtime_resume_payload()),
                'partition_states': [
                    {
                        'partition_id': int(state.partition_id),
                        'u': np.asarray(state.u, dtype=float).copy(),
                        'du': np.asarray(state.du, dtype=float).copy(),
                        'residual': np.asarray(state.residual, dtype=float).copy(),
                        'metadata': dict(state.metadata),
                    }
                    for state in runtime.partition_states
                ],
                'last_reduction_summary': dict(runtime.last_reduction_summary),
            }

        def _restore_attempt_state(snapshot: dict[str, object]) -> None:
            if runtime.backend_state is not None:
                runtime.local_backend.restore_runtime_state(
                    runtime.backend_state,
                    arrays=dict(snapshot.get('backend_arrays', {}) or {}),
                    payload={
                        **dict(snapshot.get('backend_payload', {}) or {}),
                        'resume_mode': 'restore-checkpoint',
                    },
                )
            partition_state_rows = list(snapshot.get('partition_states', []) or [])
            for state, saved in zip(runtime.partition_states, partition_state_rows):
                state.u = np.asarray(saved.get('u', state.u), dtype=float).copy()
                state.du = np.asarray(saved.get('du', state.du), dtype=float).copy()
                state.residual = np.asarray(saved.get('residual', state.residual), dtype=float).copy()
                state.metadata = dict(saved.get('metadata', state.metadata))
            runtime.last_reduction_summary = dict(snapshot.get('last_reduction_summary', {}) or {})

        while load_factor < 1.0 - 1.0e-12:
            increment_index = int(completed_steps + 1)
            remaining = max(0.0, 1.0 - load_factor)
            effective_step_size = min(step_size, remaining)
            factor = min(1.0, load_factor + effective_step_size)
            attempt_count += 1
            runtime.execution_state.current_increment = int(increment_index)
            attempt_state = _capture_attempt_state()
            self.telemetry.record_event(
                'increment-attempt',
                {
                    'stage_index': int(stage_index),
                    'stage_name': stage_name,
                    'increment_index': int(increment_index),
                    'attempt_index': int(attempt_count),
                    'load_factor': float(factor),
                    'step_size': float(effective_step_size),
                },
            )
            try:
                increment_result = runtime.local_backend.advance_stage_increment(
                    solved_model,
                    runtime.solver_settings,
                    runtime.backend_state,
                    stage_name=stage_name,
                    active_regions=active_regions,
                    bcs=context.bc_table,
                    loads=context.load_table,
                    load_factor=factor,
                    increment_index=increment_index,
                    increment_count=max(target_steps, increment_index),
                    stage_metadata=dict(context.metadata),
                )
                runtime.synchronize_partitions(stage_index=stage_index, increment_index=increment_index)
            except Exception as exc:
                error_text = str(exc)
                recoverable_cutback = (
                    isinstance(exc, RecoverableIncrementError)
                    or bool(getattr(exc, 'recoverable_cutback', False))
                    or bool(context.metadata.get('cutback_on_any_exception', False))
                )
                can_cutback = (
                    recoverable_cutback
                    and self.nonlinear_controller.failure_policy.rollback_to_stage_start
                    and max_cutbacks > 0
                    and cutback_count < max_cutbacks
                    and effective_step_size > min_step_size + 1.0e-12
                    and shrink_factor < 0.999
                )
                if can_cutback:
                    cutback_count += 1
                    _restore_attempt_state(attempt_state)
                    next_step_size = max(min_step_size, effective_step_size * shrink_factor)
                    trace_row = {
                        'step': int(increment_index),
                        'attempt': int(attempt_count),
                        'factor': float(factor),
                        'step_size': float(effective_step_size),
                        'status': 'cutback',
                        'control_reason': 'cutback',
                        'error': error_text,
                        'next_step_size': float(next_step_size),
                    }
                    step_trace_rows.append(trace_row)
                    self.result_store.increment_summaries.append(
                        {
                            'stage_index': int(stage_index),
                            'stage_name': stage_name,
                            'increment_index': int(increment_index),
                            'payload': dict(trace_row),
                        }
                    )
                    self.telemetry.record_event(
                        'increment-cutback',
                        {
                            'stage_index': int(stage_index),
                            'stage_name': stage_name,
                            'increment_index': int(increment_index),
                            'attempt_index': int(attempt_count),
                            'load_factor': float(factor),
                            'step_size': float(effective_step_size),
                            'next_step_size': float(next_step_size),
                            'cutback_count': int(cutback_count),
                            'error': error_text,
                        },
                    )
                    step_size = next_step_size
                    continue

                ok = False
                status = 'failed'
                failure_error = error_text
                _restore_attempt_state(attempt_state)
                self.telemetry.record_event(
                    'stage-failure',
                    {
                        'stage_index': int(stage_index),
                        'stage_name': stage_name,
                        'increment_index': int(increment_index),
                        'cutback_count': int(cutback_count),
                        'error': failure_error,
                    },
                )
                if (
                    self.checkpoint_manager is not None
                    and self.checkpoint_manager.policy.save_at_failure
                ):
                    checkpoint_id = self.checkpoint_manager.save_failure_checkpoint(
                        runtime,
                        int(stage_index),
                        int(increment_index),
                        payload={
                            **runtime.snapshot_state(
                                stage_index=stage_index,
                                increment_index=increment_index,
                                include_arrays=True,
                            ),
                            'error': failure_error,
                            'stage_name': stage_name,
                            'cutback_count': int(cutback_count),
                        },
                    )
                break

            row = {
                'iteration': int(increment_index),
                'attempt': int(attempt_count),
                'linear_backend': 'reference',
                'load_factor': float(factor),
                'step_size': float(effective_step_size),
                'status': str(increment_result.status),
                'active_cell_count': int(increment_result.active_cell_count),
                'control_reason': 'accepted',
            }
            history_rows.append(row)
            step_trace_rows.append(
                {
                    'step': int(increment_index),
                    'attempt': int(attempt_count),
                    'factor': float(factor),
                    'step_size': float(effective_step_size),
                    'status': str(increment_result.status),
                    'control_reason': 'accepted',
                }
            )
            self.result_store.increment_summaries.append(
                {
                    'stage_index': int(stage_index),
                    'stage_name': stage_name,
                    'increment_index': int(increment_index),
                    'payload': dict(row),
                }
            )
            self.telemetry.record_event(
                'increment-complete',
                {
                    'stage_index': int(stage_index),
                    'stage_name': stage_name,
                    'increment_index': int(increment_index),
                    'attempt_index': int(attempt_count),
                    'load_factor': float(factor),
                    'step_size': float(effective_step_size),
                    'active_cell_count': int(increment_result.active_cell_count),
                },
            )
            if (
                self.checkpoint_manager is not None
                and int(self.checkpoint_manager.policy.save_every_n_increments) > 0
                and increment_index % int(self.checkpoint_manager.policy.save_every_n_increments) == 0
                and (
                    factor < 1.0 - 1.0e-12
                    or not self.checkpoint_manager.policy.save_at_stage_end
                )
            ):
                self.checkpoint_manager.save_increment_checkpoint(
                    runtime,
                    int(stage_index),
                    int(increment_index),
                    payload={
                        **runtime.snapshot_state(
                            stage_index=stage_index,
                            increment_index=increment_index,
                            include_arrays=True,
                        ),
                        'stage_name': stage_name,
                        'load_factor': float(factor),
                        'increment_status': str(increment_result.status),
                    },
                )
            load_factor = float(factor)
            completed_steps += 1
            if load_factor >= 1.0 - 1.0e-12:
                break
            step_size = min(
                max_step_size,
                max(min_step_size, effective_step_size * growth_factor),
            )

        if increment_result is None and ok:
            status = 'skipped'
        elif increment_result is not None and ok:
            commit_info = runtime.local_backend.commit_stage(
                solved_model,
                runtime.backend_state,
                stage_name=stage_name,
                increment_result=increment_result,
                history_rows=history_rows,
                step_trace_rows=step_trace_rows,
            )
            status = str(commit_info.get('status', increment_result.status))

        solver_history = dict(solved_model.metadata.get('solver_history', {}) or {})
        solver_history[stage_name] = [dict(row) for row in history_rows]
        solved_model.metadata['solver_history'] = solver_history
        step_trace = dict(solved_model.metadata.get('step_control_trace', {}) or {})
        step_trace[stage_name] = [dict(row) for row in step_trace_rows]
        solved_model.metadata['step_control_trace'] = step_trace

        fields = solved_model.results_for_stage(stage_name)
        for field in fields:
            self.result_store.capture_field(field)

        stage_summary = self._record_stage_summary(
            stage_index=stage_index,
            context=context,
            fields=fields,
            status=status,
            increment_count=len(step_trace_rows),
            iteration_count=len(history_rows),
        )
        if failure_error is not None:
            stage_summary['error'] = failure_error
        stage_summary['accepted_increment_count'] = int(completed_steps)
        stage_summary['attempt_count'] = int(attempt_count)
        stage_summary['cutback_count'] = int(cutback_count)
        stage_summary['final_load_factor'] = float(load_factor)
        if commit_info.get('assembly_info'):
            stage_summary['assembly_info'] = dict(commit_info.get('assembly_info', {}) or {})
        linear_system_diagnostics = self._build_linear_system_diagnostics(
            stage_index=stage_index,
            stage_name=stage_name,
            execution_path='stage-executor',
            status=str(status),
            stage_summary=stage_summary,
            stage_linear_system_plan=dict(context.metadata.get('stage_linear_system_plan', {}) or {}),
            operator_summary=dict(
                dict(commit_info.get('assembly_info', {}) or {}).get('operator_summary', {}) or {}
            ),
            partition_linear_systems=list(
                dict(commit_info.get('assembly_info', {}) or {}).get('partition_linear_systems', []) or []
            ),
        )
        stage_summary['linear_system_diagnostics_summary'] = self._compact_linear_system_diagnostics(
            linear_system_diagnostics
        )
        self.result_store.stage_summaries.append(stage_summary)
        stage_asset = {
            'stage_index': int(stage_index),
            'stage_name': stage_name,
            'execution_path': 'stage-executor',
            'status': str(status),
            'stage_summary': dict(stage_summary),
            'assembly_info': dict(commit_info.get('assembly_info', {}) or {}),
            'operator_summary': dict(
                dict(commit_info.get('assembly_info', {}) or {}).get('operator_summary', {}) or {}
            ),
            'partition_linear_systems': list(
                dict(commit_info.get('assembly_info', {}) or {}).get('partition_linear_systems', []) or []
            ),
            'stage_linear_system_plan': dict(context.metadata.get('stage_linear_system_plan', {}) or {}),
            'linear_system_diagnostics': dict(linear_system_diagnostics),
        }
        self.result_store.capture_stage_asset(stage_asset)
        self.telemetry.record_event(
            'stage-summary',
            {
                **stage_summary,
                'duration_seconds': float(perf_counter() - started),
            },
        )

        if (
            ok
            and self.checkpoint_manager is not None
            and self.checkpoint_manager.policy.save_at_stage_end
        ):
            checkpoint_id = self.checkpoint_manager.save_stage_checkpoint(
                runtime,
                int(stage_index),
                payload={
                    **runtime.snapshot_state(stage_index=stage_index, include_arrays=True),
                    'stage_summary': stage_summary,
                },
            )

        return StageRunReport(
            stage_index=int(stage_index),
            stage_name=stage_name,
            ok=ok,
            status=status,
            active_cell_count=int(stage_summary['active_cell_count']),
            active_region_count=int(stage_summary['active_region_count']),
            increment_count=int(stage_summary['increment_count']),
            iteration_count=int(stage_summary['iteration_count']),
            field_names=tuple(field.name for field in fields),
            checkpoint_id=checkpoint_id,
            metadata={
                'history_rows': len(history_rows),
                'step_trace_rows': len(step_trace_rows),
                'execution_path': 'stage-executor',
                'error': failure_error,
                'accepted_increment_count': int(completed_steps),
                'attempt_count': int(attempt_count),
                'cutback_count': int(cutback_count),
                'final_load_factor': float(load_factor),
                'partition_activity': dict(context.metadata.get('partition_activity', {}) or {}),
                'assembly_info': dict(commit_info.get('assembly_info', {}) or {}),
                'linear_system_diagnostics': dict(linear_system_diagnostics),
            },
        )

    def run_stage(self, stage_index, context, solved_model, runtime) -> StageRunReport:
        if getattr(runtime, 'stage_execution_supported', False):
            return self._run_stage_execution(stage_index, context, solved_model, runtime)
        return self._run_postprocessed_stage(stage_index, context, solved_model, runtime)
