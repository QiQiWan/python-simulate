from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('pyvista')

from geoai_simkit.core.types import ResultField
from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import AnalysisTaskSpec, GeneralFEMSolver
from geoai_simkit.pipeline import AnalysisCaseSpec, BoundaryConditionSpec, GeometrySource, MaterialAssignmentSpec, MeshAssemblySpec
from geoai_simkit.runtime import CheckpointManager, CheckpointPolicy
from geoai_simkit.runtime import CompileConfig, RuntimeCompiler, RuntimeConfig
from geoai_simkit.runtime import RecoverableIncrementError
from geoai_simkit.solver.backends import ReferenceBackend


def test_runtime_compiler_builds_partitioned_bundle_from_demo_case() -> None:
    solver = GeneralFEMSolver()
    prepared = solver.prepare_case(build_demo_case())
    bundle = RuntimeCompiler().compile_case(prepared, CompileConfig(partition_count=2))
    assert bundle.compile_report.ok is True
    assert bundle.runtime_model.node_count > 0
    assert bundle.runtime_model.cell_count > 0
    assert len(bundle.partitioned_model.partitions) == 2
    assert bundle.partitioned_model.numbering.global_dof_count == bundle.runtime_model.node_count * bundle.runtime_model.dof_per_node
    assert bundle.partitioned_model.stage_plan.stage_names[:2] == ('initial', 'wall_activation')
    assert bundle.compile_report.metadata['estimated_peak_memory_bytes'] > 0
    assert len(bundle.compile_report.metadata['cells_per_partition']) == 2
    assert len(bundle.compile_report.metadata['gp_states_per_partition']) == 2
    assert len(bundle.compile_report.metadata['owned_nodes_per_partition']) == 2
    assert len(bundle.compile_report.metadata['owned_dofs_per_partition']) == 2
    assert len(bundle.compile_report.metadata['comm_bytes_per_partition']) == 2
    assert len(bundle.compile_report.metadata['linear_system_partition_estimates']) == 2
    assert len(bundle.compile_report.metadata['stage_linear_system_plans']) == len(bundle.runtime_model.stage_plan.stage_names)
    assert bundle.compile_report.metadata['estimated_comm_bytes_per_increment'] >= 0
    assert bundle.compile_report.metadata['node_balance_ratio'] >= 1.0
    assert bundle.compile_report.metadata['max_neighbor_count'] >= 0
    assert bundle.compile_report.metadata['stage_partition_diagnostics']
    assert bundle.compile_report.metadata['partition_advisory']['current_partition_count'] == 2
    first_stage = bundle.compile_report.metadata['stage_partition_diagnostics'][0]
    assert len(first_stage['active_cells_per_partition']) == 2
    assert len(first_stage['active_owned_nodes_per_partition']) == 2
    assert len(first_stage['active_owned_dofs_per_partition']) == 2
    first_stage_plan = bundle.compile_report.metadata['stage_linear_system_plans'][0]
    assert len(first_stage_plan['partition_local_systems']) == 2
    assert first_stage_plan['estimated_matrix_storage_bytes'] >= 0


def test_general_solver_emits_runtime_reports_and_result_db(tmp_path) -> None:
    class FakeBackend:
        def solve(self, model, settings):
            grid = model.to_unstructured_grid()
            stage_names = [stage.name for stage in model.stages] or ['default']
            for index, stage_name in enumerate(stage_names, start=1):
                u = np.full((grid.n_points, 3), float(index), dtype=float)
                model.add_result(ResultField(name='U', association='point', values=u, components=3, stage=stage_name))
                model.add_result(ResultField(name='U_mag', association='point', values=np.linalg.norm(u, axis=1), stage=stage_name))
            model.metadata['stages_run'] = stage_names
            model.metadata['solver_history'] = {stage_name: [{'iteration': 1, 'linear_backend': 'fake'}] for stage_name in stage_names}
            model.metadata['step_control_trace'] = {stage_name: [{'step': 1, 'factor': 1.0}] for stage_name in stage_names}
            model.metadata['solver_mode'] = 'fake-runtime'
            return model

    solver = GeneralFEMSolver(backend=FakeBackend())
    task = AnalysisTaskSpec(
        case=build_demo_case(),
        execution_profile='cpu-robust',
        compile_config=CompileConfig(partition_count=2),
        runtime_config=RuntimeConfig(partition_count=2, metadata={'checkpoint_dir': str(tmp_path / 'checkpoints')}),
    )
    result = solver.run_task(task)
    assert result.compile_report is not None and result.compile_report.ok is True
    assert result.runtime_report is not None and result.runtime_report.ok is True
    assert result.result_db is not None and result.result_db.field_labels()
    assert result.metadata['compile_report']['partition_count'] == 2
    assert 'runtime_metadata' in result.metadata
    assert 0 < len(result.metadata['checkpoint_ids']) <= len(result.runtime_report.stage_reports)


def test_runtime_uses_stage_executor_when_backend_supports_stage_execution(tmp_path) -> None:
    class FakeStageBackend:
        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {
                'u': np.zeros((grid.n_points, 3), dtype=float),
                'stress': np.zeros((grid.n_cells, 6), dtype=float),
                'vm': np.zeros(grid.n_cells, dtype=float),
                'stages': [],
            }

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            runtime_state['u'] = np.full((grid.n_points, 3), float(load_factor), dtype=float)
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': runtime_state['u'].copy(),
                    'cell_stress_full': runtime_state['stress'].copy(),
                    'cell_vm_full': runtime_state['vm'].copy(),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-stage'},
                },
            )()

        def commit_stage(
            self,
            model,
            runtime_state,
            *,
            stage_name: str,
            increment_result,
            history_rows=None,
            step_trace_rows=None,
        ):
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=increment_result.total_u.copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            runtime_state['stages'].append(stage_name)
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['solver_backend'] = 'fake-stage'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {'total_u': runtime_state['u']}

        def capture_runtime_resume_payload(self, runtime_state):
            return {'stages': list(runtime_state['stages'])}

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            if 'total_u' in arrays:
                runtime_state['u'] = np.asarray(arrays['total_u'], dtype=float).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]

        def solve(self, model, settings):
            raise AssertionError('stage-aware runtime should not call full-model solve()')

    solver = GeneralFEMSolver(backend=FakeStageBackend())
    task = AnalysisTaskSpec(
        case=build_demo_case(),
        execution_profile='cpu-robust',
        compile_config=CompileConfig(partition_count=2),
        runtime_config=RuntimeConfig(
            partition_count=2,
            metadata={'checkpoint_dir': str(tmp_path / 'checkpoints')},
        ),
    )
    result = solver.run_task(task)
    assert result.runtime_report is not None
    assert result.runtime_report.metadata['execution_mode'] == 'stage-executor'
    assert result.runtime_report.metadata['stage_execution_diagnostics']['supported'] is True
    assert result.runtime_report.metadata['stage_linear_system_plans']
    assert result.runtime_report.metadata['stage_asset_count'] >= 1
    assert result.runtime_report.metadata['stage_linear_system_diagnostics_count'] >= 1
    assert result.runtime_report.metadata['stage_assets']
    assert result.runtime_report.metadata['linear_system_diagnostics_summary']['stage_count'] >= 1
    assert result.runtime_report.metadata['linear_system_diagnostics_summary']['ok'] is True
    assert result.solved_model.metadata['solver_backend'] == 'fake-stage'
    assert result.result_db is not None
    assert result.result_db.stage_names()
    assert result.runtime_report.metadata['last_reduction_summary']['active_partitions'] >= 1
    assert result.runtime_report.metadata['partition_diagnostics']
    assert result.runtime_report.metadata['bootstrap_summary']['device_contexts']


def test_checkpoint_manager_persists_numeric_assets(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path, policy=CheckpointPolicy())
    checkpoint_id = manager.save_stage_checkpoint(
        runtime=type(
            'RuntimeStub',
            (),
            {
                'telemetry': type('TelemetryStub', (), {'record_event': lambda *args, **kwargs: None})(),
                'execution_state': type('StateStub', (), {'last_checkpoint_id': None})(),
                'snapshot_state': lambda *args, **kwargs: {
                    'case_name': 'demo',
                    '_array_payloads': {'total_u': np.ones((2, 3), dtype=float)},
                },
            },
        )(),
        stage_index=0,
    )
    payload = manager.load_checkpoint(checkpoint_id)
    assert payload['array_asset'].endswith('.npz')
    assert 'arrays' in payload
    assert payload['arrays']['total_u'].shape == (2, 3)


def test_checkpoint_manager_retention_is_scoped_per_checkpoint_kind(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path, policy=CheckpointPolicy(keep_last_n=1))
    runtime_stub = type(
        'RuntimeStub',
        (),
        {
            'telemetry': type('TelemetryStub', (), {'record_event': lambda *args, **kwargs: None})(),
            'execution_state': type('StateStub', (), {'last_checkpoint_id': None})(),
            'snapshot_state': lambda *args, **kwargs: {
                'case_name': 'demo',
                '_array_payloads': {'total_u': np.ones((2, 3), dtype=float)},
            },
        },
    )()
    stage_0 = manager.save_stage_checkpoint(runtime_stub, stage_index=0)
    failure_0 = manager.save_failure_checkpoint(runtime_stub, stage_index=0, increment_index=1)
    stage_1 = manager.save_stage_checkpoint(runtime_stub, stage_index=1)

    checkpoint_ids = manager.list_checkpoint_ids()
    assert stage_0 not in checkpoint_ids
    assert stage_1 in checkpoint_ids
    assert failure_0 in checkpoint_ids
    assert not (tmp_path / f'{stage_0}.json').exists()
    assert (tmp_path / f'{failure_0}.json').exists()


def test_checkpoint_manager_resolves_latest_selectors(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path, policy=CheckpointPolicy(keep_last_n=5))
    runtime_stub = type(
        'RuntimeStub',
        (),
        {
            'telemetry': type('TelemetryStub', (), {'record_event': lambda *args, **kwargs: None})(),
            'execution_state': type('StateStub', (), {'last_checkpoint_id': None})(),
            'snapshot_state': lambda *args, **kwargs: {
                'case_name': 'demo',
                '_array_payloads': {'total_u': np.ones((2, 3), dtype=float)},
            },
        },
    )()
    stage_0 = manager.save_stage_checkpoint(runtime_stub, stage_index=0)
    failure_0 = manager.save_failure_checkpoint(runtime_stub, stage_index=0, increment_index=1)
    stage_1 = manager.save_stage_checkpoint(runtime_stub, stage_index=1)

    latest = manager.latest_checkpoint_ids()
    assert latest['stage'] == stage_1
    assert latest['failure'] == failure_0
    assert manager.resolve_checkpoint_id('latest-stage') == stage_1
    assert manager.resolve_checkpoint_id('failure-latest') == failure_0
    assert manager.resolve_checkpoint_id(stage_0) == stage_0


def test_checkpoint_manager_validates_restart_contract_payload(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path, policy=CheckpointPolicy(keep_last_n=5))
    runtime_stub = type(
        'RuntimeStub',
        (),
        {
            'telemetry': type('TelemetryStub', (), {'record_event': lambda *args, **kwargs: None})(),
            'execution_state': type('StateStub', (), {'last_checkpoint_id': None})(),
            'snapshot_state': lambda *args, **kwargs: {
                'runtime_schema_version': 3,
                'case_name': 'demo',
                'partition_count': 2,
                'failure_policy': {
                    'rollback_to_stage_start': True,
                    'max_stage_retries': 1,
                    'max_increment_cutbacks': 2,
                    'write_failure_checkpoint': True,
                },
                'solver_policy': {
                    'nonlinear_max_iterations': 12,
                    'tolerance': 1.0e-6,
                    'line_search': False,
                    'max_cutbacks': 2,
                    'preconditioner': 'auto',
                    'solver_strategy': 'auto',
                },
                'telemetry_summary': {'event_count': 1},
                'result_store_summary': {'stage_count': 1, 'field_count': 0},
                'partition_layout_metadata': [
                    {'partition_id': 0, 'owned_cell_count': 2},
                    {'partition_id': 1, 'owned_cell_count': 2},
                ],
                'numbering_metadata': [
                    {'partition_id': 0, 'owned_dof_range': [0, 5]},
                    {'partition_id': 1, 'owned_dof_range': [6, 11]},
                ],
                'stage_activation_state': [
                    {'stage_index': 0, 'stage_name': 'initial', 'active_region_names': ['soil_mass'], 'active_cell_count': 4},
                ],
                'result_store': {'stage_summaries': [{'stage_name': 'initial'}], 'increment_summaries': [], 'field_snapshots': []},
                '_array_payloads': {'total_u': np.ones((2, 3), dtype=float)},
            },
        },
    )()
    checkpoint_id = manager.save_stage_checkpoint(runtime_stub, stage_index=0)
    validation = manager.validate_checkpoint('latest-stage')
    assert validation['checkpoint_id'] == checkpoint_id
    assert validation['requested_checkpoint_id'] == 'latest-stage'
    assert validation['ok'] is True
    assert validation['partition_layout_count'] == 2
    assert validation['numbering_count'] == 2
    assert validation['missing_field_array_count'] == 0
    assert validation['array_shape_issue_count'] == 0


def test_runtime_rejects_invalid_resume_checkpoint_contract(tmp_path: Path) -> None:
    class FakeStageBackend:
        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {'u': np.zeros((grid.n_points, 3), dtype=float)}

        def solve(self, model, settings):
            raise AssertionError('invalid resume should fail before solve()')

    checkpoint_dir = tmp_path / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / 'stage-000.json').write_text(
        '{"kind": "stage", "case_name": "demo", "execution_state": {}, "result_store": {}}',
        encoding='utf-8',
    )

    solver = GeneralFEMSolver(backend=FakeStageBackend())
    with pytest.raises(RuntimeError, match='failed validation'):
        solver.run_task(
            AnalysisTaskSpec(
                case=build_demo_case(),
                execution_profile='cpu-robust',
                compile_config=CompileConfig(partition_count=2),
                runtime_config=RuntimeConfig(
                    partition_count=2,
                    metadata={
                        'checkpoint_dir': str(checkpoint_dir),
                        'resume_checkpoint_id': 'stage-000',
                    },
                ),
            )
        )


def test_runtime_can_resume_from_stage_checkpoint(tmp_path) -> None:
    class FakeResumeBackend:
        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {
                'u': np.zeros((grid.n_points, 3), dtype=float),
                'stages': [],
                'history': {},
            }

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            value = float(len(runtime_state['stages']) + load_factor)
            total_u = np.full((grid.n_points, 3), value, dtype=float)
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': total_u,
                    'cell_stress_full': np.zeros((grid.n_cells, 6), dtype=float),
                    'cell_vm_full': np.zeros(grid.n_cells, dtype=float),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-resume'},
                },
            )()

        def commit_stage(
            self,
            model,
            runtime_state,
            *,
            stage_name: str,
            increment_result,
            history_rows=None,
            step_trace_rows=None,
        ):
            runtime_state['u'] = np.asarray(increment_result.total_u, dtype=float).copy()
            runtime_state['stages'].append(stage_name)
            runtime_state['history'][stage_name] = [dict(row) for row in history_rows or []]
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=runtime_state['u'].copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['solver_history'] = dict(runtime_state['history'])
            model.metadata['solver_backend'] = 'fake-resume'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {'total_u': np.asarray(runtime_state['u'], dtype=float).copy()}

        def capture_runtime_resume_payload(self, runtime_state):
            return {
                'stages': list(runtime_state['stages']),
                'history': {
                    name: [dict(row) for row in rows]
                    for name, rows in runtime_state['history'].items()
                },
            }

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            runtime_state['u'] = np.asarray(
                arrays.get('total_u', runtime_state['u']),
                dtype=float,
            ).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]
            runtime_state['history'] = {
                str(name): [dict(row) for row in rows]
                for name, rows in dict(payload.get('history', {}) or {}).items()
            }

        def solve(self, model, settings):
            raise AssertionError('resume path should stay on stage executor')

    checkpoint_dir = tmp_path / 'checkpoints'
    solver = GeneralFEMSolver(backend=FakeResumeBackend())
    first = solver.run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={'checkpoint_dir': str(checkpoint_dir)},
            ),
        )
    )
    resume_checkpoint_id = str(first.metadata['checkpoint_ids'][0])

    resumed = solver.run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={
                    'checkpoint_dir': str(checkpoint_dir),
                    'resume_checkpoint_id': resume_checkpoint_id,
                },
            ),
        )
    )
    assert resumed.runtime_report is not None
    assert resumed.runtime_report.metadata['resumed_from_checkpoint'] == resume_checkpoint_id
    assert resumed.runtime_report.metadata['resume_checkpoint_kind'] == 'stage'
    assert resumed.runtime_report.metadata['restored_stage_count'] >= 1
    assert resumed.runtime_report.stage_reports[0].status == 'restored'
    assert resumed.result_db is not None
    assert resumed.result_db.stage_names()


def test_runtime_writes_increment_checkpoints_when_configured(tmp_path) -> None:
    class FakeIncrementBackend:
        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {'u': np.zeros((grid.n_points, 3), dtype=float), 'stages': []}

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            total_u = np.full((grid.n_points, 3), float(increment_index), dtype=float)
            runtime_state['u'] = total_u.copy()
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': total_u,
                    'cell_stress_full': np.zeros((grid.n_cells, 6), dtype=float),
                    'cell_vm_full': np.zeros(grid.n_cells, dtype=float),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-increment'},
                },
            )()

        def commit_stage(self, model, runtime_state, *, stage_name: str, increment_result, history_rows=None, step_trace_rows=None):
            runtime_state['stages'].append(stage_name)
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=np.asarray(increment_result.total_u, dtype=float).copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['solver_backend'] = 'fake-increment'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {'total_u': np.asarray(runtime_state['u'], dtype=float).copy()}

        def capture_runtime_resume_payload(self, runtime_state):
            return {'stages': list(runtime_state['stages'])}

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            if 'total_u' in arrays:
                runtime_state['u'] = np.asarray(arrays['total_u'], dtype=float).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]

        def solve(self, model, settings):
            raise AssertionError('increment-checkpoint path should stay on stage executor')

    checkpoint_dir = tmp_path / 'checkpoints'
    result = GeneralFEMSolver(backend=FakeIncrementBackend()).run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                checkpoint_policy='incremental',
                metadata={
                    'checkpoint_dir': str(checkpoint_dir),
                    'checkpoint_every_n_increments': 1,
                    'checkpoint_keep_last_n': 20,
                },
            ),
        )
    )
    assert result.runtime_report is not None
    increment_checkpoint_ids = tuple(result.runtime_report.metadata.get('increment_checkpoint_ids', ()) or ())
    assert increment_checkpoint_ids
    assert all(str(item).startswith('increment-') for item in increment_checkpoint_ids)
    assert result.runtime_report.metadata['checkpoint_policy']['save_every_n_increments'] == 1


def test_runtime_cutback_retry_recovers_stage_execution(tmp_path) -> None:
    class FakeCutbackBackend:
        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {
                'u': np.zeros((grid.n_points, 3), dtype=float),
                'stages': [],
                'committed_factor': 0.0,
            }

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name
            runtime_state['committed_factor'] = 0.0

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            previous = float(runtime_state.get('committed_factor', 0.0) or 0.0)
            delta = float(load_factor) - previous
            if delta > 0.6:
                raise RecoverableIncrementError(f'increment too large: {delta:.3f}')
            total_u = np.full((grid.n_points, 3), float(load_factor), dtype=float)
            runtime_state['u'] = total_u.copy()
            runtime_state['committed_factor'] = float(load_factor)
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': total_u,
                    'cell_stress_full': np.zeros((grid.n_cells, 6), dtype=float),
                    'cell_vm_full': np.zeros(grid.n_cells, dtype=float),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-cutback'},
                },
            )()

        def commit_stage(self, model, runtime_state, *, stage_name: str, increment_result, history_rows=None, step_trace_rows=None):
            runtime_state['stages'].append(stage_name)
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=np.asarray(increment_result.total_u, dtype=float).copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['step_control_trace'] = {'default': [{'control_reason': 'cutback-applied'}]}
            model.metadata['solver_backend'] = 'fake-cutback'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {'total_u': np.asarray(runtime_state['u'], dtype=float).copy()}

        def capture_runtime_resume_payload(self, runtime_state):
            return {
                'stages': list(runtime_state['stages']),
                'committed_factor': float(runtime_state.get('committed_factor', 0.0) or 0.0),
            }

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            if 'total_u' in arrays:
                runtime_state['u'] = np.asarray(arrays['total_u'], dtype=float).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]
            runtime_state['committed_factor'] = float(payload.get('committed_factor', 0.0) or 0.0)

        def solve(self, model, settings):
            raise AssertionError('cutback path should stay on stage executor')

    case = build_demo_case()
    case.stages = tuple()
    result = GeneralFEMSolver(backend=FakeCutbackBackend()).run_task(
        AnalysisTaskSpec(
            case=case,
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={'checkpoint_dir': str(tmp_path / 'checkpoints')},
            ),
        )
    )
    assert result.runtime_report is not None
    assert result.runtime_report.ok is True
    assert result.runtime_report.stage_reports[0].metadata['cutback_count'] >= 1
    assert result.runtime_report.stage_reports[0].metadata['accepted_increment_count'] >= 2


def test_runtime_can_resume_from_failure_checkpoint_boundary(tmp_path) -> None:
    class FakeFailureResumeBackend:
        def __init__(self) -> None:
            self.failures_remaining = 1

        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {
                'u': np.zeros((grid.n_points, 3), dtype=float),
                'stage_start_u': np.zeros((grid.n_points, 3), dtype=float),
                'stages': [],
                'history': {},
            }

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name
            runtime_state['stage_start_u'] = np.asarray(runtime_state['u'], dtype=float).copy()

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            if stage_name == 'wall_activation' and increment_index == 1 and self.failures_remaining > 0:
                self.failures_remaining -= 1
                runtime_state['u'] = np.full((grid.n_points, 3), 99.0, dtype=float)
                raise RuntimeError('synthetic stage failure')
            value = float(len(runtime_state['stages']) + load_factor)
            total_u = np.full((grid.n_points, 3), value, dtype=float)
            runtime_state['u'] = total_u.copy()
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': total_u,
                    'cell_stress_full': np.zeros((grid.n_cells, 6), dtype=float),
                    'cell_vm_full': np.zeros(grid.n_cells, dtype=float),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-failure-resume'},
                },
            )()

        def commit_stage(
            self,
            model,
            runtime_state,
            *,
            stage_name: str,
            increment_result,
            history_rows=None,
            step_trace_rows=None,
        ):
            runtime_state['u'] = np.asarray(increment_result.total_u, dtype=float).copy()
            runtime_state['stages'].append(stage_name)
            runtime_state['history'][stage_name] = [dict(row) for row in history_rows or []]
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=runtime_state['u'].copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['solver_history'] = dict(runtime_state['history'])
            model.metadata['solver_backend'] = 'fake-failure-resume'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {
                'total_u': np.asarray(runtime_state['u'], dtype=float).copy(),
                'stage_start_total_u': np.asarray(runtime_state['stage_start_u'], dtype=float).copy(),
            }

        def capture_runtime_resume_payload(self, runtime_state):
            return {
                'stages': list(runtime_state['stages']),
                'history': {
                    name: [dict(row) for row in rows]
                    for name, rows in runtime_state['history'].items()
                },
                'active_stage': runtime_state.get('active_stage'),
            }

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            runtime_state['stage_start_u'] = np.asarray(
                arrays.get('stage_start_total_u', runtime_state['stage_start_u']),
                dtype=float,
            ).copy()
            if str(payload.get('resume_mode')) == 'rollback-stage-start' and 'stage_start_total_u' in arrays:
                runtime_state['u'] = runtime_state['stage_start_u'].copy()
            else:
                runtime_state['u'] = np.asarray(
                    arrays.get('total_u', runtime_state['u']),
                    dtype=float,
                ).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]
            runtime_state['history'] = {
                str(name): [dict(row) for row in rows]
                for name, rows in dict(payload.get('history', {}) or {}).items()
            }
            runtime_state['active_stage'] = payload.get('active_stage')

        def solve(self, model, settings):
            raise AssertionError('failure resume path should stay on stage executor')

    checkpoint_dir = tmp_path / 'checkpoints'
    backend = FakeFailureResumeBackend()
    solver = GeneralFEMSolver(backend=backend)

    first = solver.run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={'checkpoint_dir': str(checkpoint_dir)},
            ),
        )
    )
    assert first.runtime_report is not None
    assert first.runtime_report.ok is False
    failure_checkpoint_ids = tuple(first.metadata.get('failure_checkpoint_ids', ()) or ())
    assert failure_checkpoint_ids
    failure_checkpoint_id = str(failure_checkpoint_ids[-1])

    resumed = solver.run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={
                    'checkpoint_dir': str(checkpoint_dir),
                    'resume_checkpoint_id': failure_checkpoint_id,
                },
            ),
        )
    )
    assert resumed.runtime_report is not None
    assert resumed.runtime_report.ok is True
    assert resumed.runtime_report.metadata['resumed_from_checkpoint'] == failure_checkpoint_id
    assert resumed.runtime_report.metadata['resume_checkpoint_kind'] == 'failure'
    assert resumed.runtime_report.stage_reports[0].status == 'restored'
    assert any(
        report.stage_name == 'wall_activation' and report.status == 'completed'
        for report in resumed.runtime_report.stage_reports
    )
    assert resumed.solved_model.metadata['solver_backend'] == 'fake-failure-resume'

    resumed_latest = solver.run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={
                    'checkpoint_dir': str(checkpoint_dir),
                    'resume_checkpoint_id': 'latest-failure',
                },
            ),
        )
    )
    assert resumed_latest.runtime_report is not None
    assert resumed_latest.runtime_report.ok is True
    assert resumed_latest.runtime_report.metadata['resume_checkpoint_selector'] == 'latest-failure'
    assert resumed_latest.runtime_report.metadata['resumed_from_checkpoint'] == failure_checkpoint_id


def test_runtime_retries_failed_stage_from_stage_start_boundary(tmp_path) -> None:
    class FakeStageRetryBackend:
        def __init__(self) -> None:
            self.failures_remaining = 1

        def supports_stage_execution(self, model, settings):
            return True

        def initialize_runtime_state(self, model, settings):
            grid = model.to_unstructured_grid()
            model.clear_results()
            return {
                'u': np.zeros((grid.n_points, 3), dtype=float),
                'stage_start_u': np.zeros((grid.n_points, 3), dtype=float),
                'stages': [],
                'history': {},
            }

        def begin_stage(self, runtime_state, *, stage_name: str) -> None:
            runtime_state['active_stage'] = stage_name
            runtime_state['stage_start_u'] = np.asarray(runtime_state['u'], dtype=float).copy()

        def advance_stage_increment(
            self,
            model,
            settings,
            runtime_state,
            *,
            stage_name: str,
            active_regions,
            bcs,
            loads,
            load_factor: float,
            increment_index: int,
            increment_count: int,
            stage_metadata=None,
        ):
            grid = model.to_unstructured_grid()
            if stage_name == 'wall_activation' and increment_index == 1 and self.failures_remaining > 0:
                self.failures_remaining -= 1
                runtime_state['u'] = np.full((grid.n_points, 3), 77.0, dtype=float)
                raise RuntimeError('synthetic retryable stage failure')
            value = float(len(runtime_state['stages']) + load_factor)
            total_u = np.full((grid.n_points, 3), value, dtype=float)
            runtime_state['u'] = total_u.copy()
            return type(
                'IncrementResult',
                (),
                {
                    'status': 'completed',
                    'active_cell_count': int(grid.n_cells),
                    'iteration_count': 1,
                    'total_u': total_u,
                    'cell_stress_full': np.zeros((grid.n_cells, 6), dtype=float),
                    'cell_vm_full': np.zeros(grid.n_cells, dtype=float),
                    'assembly_info': {'stage_name': stage_name, 'solver_path': 'fake-stage-retry'},
                },
            )()

        def commit_stage(self, model, runtime_state, *, stage_name: str, increment_result, history_rows=None, step_trace_rows=None):
            runtime_state['u'] = np.asarray(increment_result.total_u, dtype=float).copy()
            runtime_state['stages'].append(stage_name)
            runtime_state['history'][stage_name] = [dict(row) for row in history_rows or []]
            model.add_result(
                ResultField(
                    name='U',
                    association='point',
                    values=runtime_state['u'].copy(),
                    components=3,
                    stage=stage_name,
                )
            )
            return {'status': 'completed'}

        def finalize_runtime_state(self, model, settings, runtime_state):
            model.metadata['stages_run'] = list(runtime_state['stages'])
            model.metadata['solver_history'] = dict(runtime_state['history'])
            model.metadata['solver_backend'] = 'fake-stage-retry'
            return model

        def capture_runtime_arrays(self, runtime_state):
            return {
                'total_u': np.asarray(runtime_state['u'], dtype=float).copy(),
                'stage_start_total_u': np.asarray(runtime_state['stage_start_u'], dtype=float).copy(),
            }

        def capture_runtime_resume_payload(self, runtime_state):
            return {
                'stages': list(runtime_state['stages']),
                'history': {
                    name: [dict(row) for row in rows]
                    for name, rows in runtime_state['history'].items()
                },
                'active_stage': runtime_state.get('active_stage'),
            }

        def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None):
            arrays = dict(arrays or {})
            payload = dict(payload or {})
            runtime_state['stage_start_u'] = np.asarray(
                arrays.get('stage_start_total_u', runtime_state['stage_start_u']),
                dtype=float,
            ).copy()
            runtime_state['u'] = np.asarray(
                arrays.get('total_u', runtime_state['u']),
                dtype=float,
            ).copy()
            runtime_state['stages'] = [str(item) for item in payload.get('stages', []) or []]
            runtime_state['history'] = {
                str(name): [dict(row) for row in rows]
                for name, rows in dict(payload.get('history', {}) or {}).items()
            }
            runtime_state['active_stage'] = payload.get('active_stage')

        def solve(self, model, settings):
            raise AssertionError('stage retry path should stay on stage executor')

    checkpoint_dir = tmp_path / 'checkpoints'
    result = GeneralFEMSolver(backend=FakeStageRetryBackend()).run_task(
        AnalysisTaskSpec(
            case=build_demo_case(),
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={
                    'checkpoint_dir': str(checkpoint_dir),
                    'max_stage_retries': 1,
                    'checkpoint_keep_last_n': 20,
                },
            ),
        )
    )
    assert result.runtime_report is not None
    assert result.runtime_report.ok is True
    assert result.runtime_report.metadata['total_stage_retry_count'] == 1
    assert result.runtime_report.metadata['stage_retry_counts']['wall_activation'] == 1
    assert any(str(item).startswith('failure-') for item in result.runtime_report.metadata['failure_checkpoint_ids'])
    wall_report = next(report for report in result.runtime_report.stage_reports if report.stage_name == 'wall_activation')
    assert wall_report.metadata['stage_retry_count'] == 1
    assert wall_report.metadata['stage_attempt_count'] == 2
    assert result.result_db is not None
    assert result.result_db.stage_names().count('wall_activation') == 1


def test_reference_runtime_partition_counts_agree_on_linear_continuum_path(tmp_path) -> None:
    scene = ParametricPitScene(length=8.0, width=4.0, depth=4.0, soil_depth=6.0, nx=4, ny=4, nz=4, wall_thickness=0.4)
    case = AnalysisCaseSpec(
        name='linear-continuum-consistency',
        geometry=GeometrySource(builder=scene.build),
        mesh=MeshAssemblySpec(merge_points=True),
        materials=(
            MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1.0e7, 'nu': 0.3, 'rho': 1800.0}),
            MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3.0e10, 'nu': 0.2, 'rho': 2500.0}),
        ),
        boundary_conditions=(
            BoundaryConditionSpec(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)),
        ),
    )
    solver = GeneralFEMSolver(backend=ReferenceBackend())
    result_single = solver.run_task(
        AnalysisTaskSpec(
            case=case,
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=1),
            runtime_config=RuntimeConfig(
                partition_count=1,
                metadata={'checkpoint_dir': str(tmp_path / 'p1_checkpoints')},
            ),
        )
    )
    result_multi = solver.run_task(
        AnalysisTaskSpec(
            case=case,
            execution_profile='cpu-robust',
            compile_config=CompileConfig(partition_count=2),
            runtime_config=RuntimeConfig(
                partition_count=2,
                metadata={'checkpoint_dir': str(tmp_path / 'p2_checkpoints')},
            ),
        )
    )
    assert result_single.runtime_report is not None and result_single.runtime_report.ok is True
    assert result_multi.runtime_report is not None and result_multi.runtime_report.ok is True
    assert result_single.result_db is not None and result_multi.result_db is not None
    assert result_single.result_db.stage_names() == result_multi.result_db.stage_names()
    assert result_multi.runtime_report.metadata['stage_partition_diagnostics']
    assert result_multi.runtime_report.metadata['stage_linear_system_plans']
    assert result_multi.runtime_report.metadata['stage_asset_count'] >= len(result_multi.runtime_report.stage_reports)
    assert result_multi.runtime_report.metadata['stage_linear_system_diagnostics_count'] >= len(result_multi.runtime_report.stage_reports)
    assert result_multi.runtime_report.metadata['partition_advisory']['current_partition_count'] == 2
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['stage_count'] >= 1
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['stages_with_actual_partition_local_systems_count'] >= 1
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['actual_global_dof_total'] > 0
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['actual_global_rhs_size_total'] > 0
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['stages_with_actual_rhs_summary_count'] >= 1
    assert result_multi.runtime_report.metadata['linear_system_diagnostics_summary']['stages_with_residual_summary_count'] >= 1
    first_stage_diag = result_multi.runtime_report.metadata['stage_partition_diagnostics'][0]
    assert len(first_stage_diag['active_owned_nodes_per_partition']) == 2
    assert len(first_stage_diag['active_owned_dofs_per_partition']) == 2
    linear_assembly = dict(result_multi.solved_model.metadata.get('linear_element_assembly', {}) or {})
    assert linear_assembly
    first_stage_meta = next(iter(linear_assembly.values()))
    assert first_stage_meta['active_node_count'] > 0
    assert 'active_partition_count' in first_stage_meta
    assert 'operator_summary' in first_stage_meta
    assert 'partition_linear_systems' in first_stage_meta
    assert len(first_stage_meta['partition_linear_systems']) == 2
    assert first_stage_meta['partition_linear_systems'][0]['has_actual_local_matrix'] is True
    assert first_stage_meta['partition_linear_systems'][0]['summary_source'] == 'runtime-assembled-global-slice'
    assert first_stage_meta['partition_linear_systems'][0]['rhs_size'] >= 0
    assert 'fixed_local_dof_count' in first_stage_meta['partition_linear_systems'][0]
    assert 'residual_norm' in first_stage_meta['partition_linear_systems'][0]
    assert 'reaction_norm' in first_stage_meta['partition_linear_systems'][0]
    assert first_stage_meta['operator_summary']['linear_system']['matrix']['block_size'] == 3
    assert first_stage_meta['operator_summary']['linear_system']['rhs_size'] > 0
    assert first_stage_meta['operator_summary']['linear_system']['shape'][0] > 0
    assert first_stage_meta['operator_summary']['linear_system']['residual_size'] > 0
    assert first_stage_meta['operator_summary']['linear_system']['reaction_size'] > 0
    assert result_multi.result_store is not None
    assert result_multi.result_store.stage_assets
    first_stage_asset = dict(result_multi.result_store.stage_assets[0])
    assert first_stage_asset['linear_system_diagnostics']['has_actual_operator_summary'] is True
    assert first_stage_asset['linear_system_diagnostics']['actual_global_dof_count'] > 0
    assert first_stage_asset['linear_system_diagnostics']['actual_global_rhs_size'] > 0
    assert first_stage_asset['linear_system_diagnostics']['actual_partition_rhs_size_total'] > 0
    assert first_stage_asset['linear_system_diagnostics']['actual_global_residual_norm'] >= 0.0
    assert first_stage_asset['linear_system_diagnostics']['actual_global_reaction_norm'] >= 0.0
    assert first_stage_asset['linear_system_diagnostics']['actual_matrix_storage_bytes'] >= 0
    assert first_stage_asset['linear_system_diagnostics']['consistency_level'] == 'full'
    assert 'runtime-assembled-global-slice' in first_stage_asset['linear_system_diagnostics']['partition_row_sources']
    assert result_multi.runtime_report.metadata['last_reduction_summary']['residual_norm'] >= 0.0
    assert result_multi.runtime_report.metadata['last_reduction_summary']['reaction_norm'] >= 0.0
    first_stage_report = result_multi.runtime_report.stage_reports[0]
    assert 'residual' in first_stage_report.field_names
    assert 'reaction' in first_stage_report.field_names
    manager = CheckpointManager(tmp_path / 'p2_checkpoints')
    stage_checkpoint_id = str(result_multi.runtime_report.metadata['stage_checkpoint_ids'][0])
    checkpoint_payload = manager.load_checkpoint(stage_checkpoint_id)
    assert 'residual' in checkpoint_payload['arrays']
    assert 'reaction' in checkpoint_payload['arrays']
    assert checkpoint_payload['arrays']['residual'].shape == checkpoint_payload['arrays']['total_u'].shape
    assert checkpoint_payload['arrays']['reaction'].shape == checkpoint_payload['arrays']['total_u'].shape
    checkpoint_summary = manager.describe_checkpoint(stage_checkpoint_id)
    first_stage_name = result_multi.result_db.stage_names()[0]
    assert f'residual@{first_stage_name}' in checkpoint_summary['field_labels']
    assert f'reaction@{first_stage_name}' in checkpoint_summary['field_labels']
    assert checkpoint_summary['stage_field_names'][first_stage_name].count('residual') == 1
    assert checkpoint_summary['stage_field_names'][first_stage_name].count('reaction') == 1
    assert checkpoint_summary['array_shapes']['residual'] == list(checkpoint_payload['arrays']['residual'].shape)
    for stage_name in result_single.result_db.stage_names():
        for field_name in ('U', 'residual', 'reaction', 'residual_mag', 'reaction_mag'):
            left_values = next(
                np.asarray(field.values, dtype=float)
                for field in result_single.result_db.fields
                if field.name == field_name and field.stage == stage_name
            )
            right_values = next(
                np.asarray(field.values, dtype=float)
                for field in result_multi.result_db.fields
                if field.name == field_name and field.stage == stage_name
            )
            assert np.allclose(left_values, right_values, rtol=1.0e-8, atol=1.0e-8)
