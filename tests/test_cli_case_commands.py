from __future__ import annotations

import json

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.cli import build_parser, main
from geoai_simkit.runtime import CheckpointManager, CheckpointPolicy


def test_cli_parser_supports_case_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(['export-demo-case', '--out', 'demo.json'])
    assert args.cmd == 'export-demo-case'
    args = parser.parse_args(['prepare-case', 'demo.json'])
    assert args.cmd == 'prepare-case'
    args = parser.parse_args(['run-case', 'demo.json', '--out-dir', 'exports', '--resume-checkpoint-id', 'stage-000', '--checkpoint-every', '2', '--checkpoint-keep-last', '5', '--max-cutbacks', '7', '--max-stage-retries', '2'])
    assert args.cmd == 'run-case'
    assert args.resume_checkpoint_id == 'stage-000'
    assert args.checkpoint_every == 2
    assert args.checkpoint_keep_last == 5
    assert args.max_cutbacks == 7
    assert args.max_stage_retries == 2
    args = parser.parse_args(['checkpoint-list', 'runtime/checkpoints'])
    assert args.cmd == 'checkpoint-list'
    args = parser.parse_args(['checkpoint-show', 'runtime/checkpoints', 'stage-000'])
    assert args.cmd == 'checkpoint-show'
    args = parser.parse_args(['checkpoint-validate', 'runtime/checkpoints', 'latest-stage'])
    assert args.cmd == 'checkpoint-validate'
    assert args.checkpoint_id == 'latest-stage'
    args = parser.parse_args(['partition-case', 'demo.json', '--partition-count', '2'])
    assert args.cmd == 'partition-case'
    args = parser.parse_args(['compare-partitions-case', 'demo.json', '--partition-count', '3', '--abs-tol', '1e-7', '--rel-tol', '1e-6'])
    assert args.cmd == 'compare-partitions-case'
    assert args.partition_count == 3
    assert args.abs_tol == pytest.approx(1.0e-7)
    assert args.rel_tol == pytest.approx(1.0e-6)


def test_export_and_prepare_case_commands(tmp_path, capsys) -> None:
    case_path = tmp_path / 'pit_case.json'
    main(['export-demo-case', '--out', str(case_path)])
    assert case_path.exists()
    main(['prepare-case', str(case_path)])
    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured[captured.find('{'):])
    assert payload['case_name'] == 'pit-demo'
    assert payload['n_points'] > 0 and payload['n_cells'] > 0


def test_checkpoint_cli_commands_emit_structured_payload(tmp_path, capsys) -> None:
    manager = CheckpointManager(tmp_path, policy=CheckpointPolicy())
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
                'execution_state': {'committed_stage_index': 0, 'committed_increment': 1},
                'failure_policy': {
                    'rollback_to_stage_start': True,
                    'max_stage_retries': 1,
                    'max_increment_cutbacks': 2,
                    'write_failure_checkpoint': True,
                },
                'solver_policy': {
                    'nonlinear_max_iterations': 8,
                    'tolerance': 1.0e-6,
                    'line_search': False,
                    'max_cutbacks': 2,
                    'preconditioner': 'auto',
                    'solver_strategy': 'auto',
                },
                'telemetry_summary': {'event_count': 0},
                'result_store_summary': {
                    'stage_count': 1,
                    'field_count': 1,
                    'stage_asset_count': 1,
                    'stage_linear_system_diagnostics_count': 1,
                },
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
                'result_store': {
                    'metadata': {
                        'stage_linear_system_plans': [
                            {'stage_index': 0, 'stage_name': 'initial', 'partition_local_systems': [{'partition_id': 0}]}
                        ],
                        'linear_system_diagnostics_summary': {'stage_count': 1},
                    },
                    'stage_summaries': [{'stage_name': 'initial'}],
                    'increment_summaries': [],
                    'field_snapshots': [
                        {
                            'name': 'U',
                            'association': 'point',
                            'components': 3,
                            'stage': 'initial',
                            'array_key': 'result_field_0000',
                        }
                    ],
                    'stage_assets': [
                        {
                            'stage_name': 'initial',
                            'linear_system_diagnostics': {'stage_name': 'initial', 'actual_matrix_storage_bytes': 256},
                        }
                    ],
                },
                '_array_payloads': {
                    'total_u': [[1.0, 0.0, 0.0]],
                    'residual': [[0.0, 0.0, 0.0]],
                    'reaction': [[0.0, 0.0, 0.0]],
                    'result_field_0000': [[1.0, 0.0, 0.0]],
                },
            },
        },
    )()
    checkpoint_id = manager.save_stage_checkpoint(runtime_stub, stage_index=0)

    main(['checkpoint-list', str(tmp_path)])
    list_payload = json.loads(capsys.readouterr().out.strip())
    assert checkpoint_id in list_payload['checkpoint_ids']
    assert list_payload['checkpoint_count'] >= 1
    assert list_payload['checkpoint_kind_counts']['stage'] >= 1
    assert list_payload['latest_checkpoint_ids']['stage'] == checkpoint_id

    main(['checkpoint-show', str(tmp_path), checkpoint_id])
    show_payload = json.loads(capsys.readouterr().out.strip())
    assert show_payload['checkpoint_id'] == checkpoint_id
    assert show_payload['kind'] == 'stage'
    assert show_payload['stage_asset_count'] == 1
    assert show_payload['stage_linear_system_plan_count'] == 1
    assert show_payload['stage_linear_system_diagnostics_count'] == 1
    assert 'U@initial' in show_payload['field_labels']
    assert show_payload['stage_field_names']['initial'] == ['U']
    assert show_payload['array_shapes']['residual'] == [1, 3]
    assert show_payload['missing_field_array_keys'] == []

    main(['checkpoint-show', str(tmp_path), 'latest'])
    latest_payload = json.loads(capsys.readouterr().out.strip())
    assert latest_payload['checkpoint_id'] == checkpoint_id
    assert latest_payload['requested_checkpoint_id'] == 'latest'

    main(['checkpoint-validate', str(tmp_path), 'latest-stage'])
    validate_payload = json.loads(capsys.readouterr().out.strip())
    assert validate_payload['checkpoint_id'] == checkpoint_id
    assert validate_payload['requested_checkpoint_id'] == 'latest-stage'
    assert validate_payload['ok'] is True
    assert validate_payload['stage_asset_count'] == 1
    assert validate_payload['stage_linear_system_plan_count'] == 1
    assert validate_payload['stage_linear_system_diagnostics_count'] == 1
    assert validate_payload['missing_field_array_count'] == 0
    assert validate_payload['array_shape_issue_count'] == 0


def test_run_case_cli_emits_runtime_summary(tmp_path, capsys) -> None:
    case_path = tmp_path / 'pit_case.json'
    main(['export-demo-case', '--out', str(case_path)])
    capsys.readouterr()
    out_dir = tmp_path / 'exports'
    main([
        'run-case',
        str(case_path),
        '--out-dir',
        str(out_dir),
        '--execution-profile',
        'cpu-robust',
        '--device',
        'cpu',
        '--partition-count',
        '2',
    ])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload['case_name'] == 'pit-demo'
    assert payload['compile']['partition_count'] == 2
    assert payload['compile']['partition_advisory']['current_partition_count'] == 2
    assert 'ok' in payload['runtime']
    assert 'stage_execution_diagnostics' in payload['runtime']
    assert payload['runtime']['stage_asset_count'] >= 1
    assert payload['runtime']['stage_linear_system_diagnostics_count'] >= 1
    assert len(payload['runtime']['stage_linear_system_plans']) >= 1
    assert len(payload['runtime']['linear_system_partition_estimates']) == 2
    assert payload['runtime']['linear_system_diagnostics_summary']['stage_count'] >= 1
    assert 'stages_with_actual_partition_local_systems_count' in payload['runtime']['linear_system_diagnostics_summary']
    if payload['runtime'].get('execution_mode') == 'stage-executor':
        assert payload['runtime']['linear_system_diagnostics_summary']['stages_with_actual_partition_local_systems_count'] >= 1
        assert payload['runtime']['linear_system_diagnostics_summary']['actual_global_rhs_size_total'] > 0
        assert payload['runtime']['linear_system_diagnostics_summary']['stages_with_actual_rhs_summary_count'] >= 1
        assert payload['runtime']['linear_system_diagnostics_summary']['stages_with_residual_summary_count'] >= 1
        first_stage_meta = next(iter(payload['runtime_assembly'].values()))
        assert first_stage_meta['operator_summary']['linear_system']['rhs_size'] > 0
        assert first_stage_meta['operator_summary']['linear_system']['residual_size'] > 0
        assert first_stage_meta['operator_summary']['linear_system']['reaction_size'] > 0
        assert first_stage_meta['partition_linear_systems'][0]['rhs_size'] >= 0
        assert 'residual_norm' in first_stage_meta['partition_linear_systems'][0]
        assert 'residual' in payload['runtime']['stage_reports'][0]['field_names']
        assert 'reaction' in payload['runtime']['stage_reports'][0]['field_names']
    assert payload['runtime']['stage_reports']
    assert payload['runtime']['telemetry_summary']
    assert 'runtime_assembly' in payload
