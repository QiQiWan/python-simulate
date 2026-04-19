from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from geoai_simkit._optional import require_optional_dependency
from geoai_simkit._version import __version__
from geoai_simkit.app.workbench import WorkbenchService
from geoai_simkit.env_check import collect_environment_checks, format_environment_report
from geoai_simkit.pipeline import (
    AnalysisCaseBuilder,
    AnalysisCaseValidator,
    AnalysisExportSpec,
    AnalysisTaskSpec,
    GeneralFEMSolver,
    adjacency_summary_rows,
    analyze_interface_topology,
    build_solver_settings,
    build_execution_plan,
    build_preprocessor_snapshot,
    compute_interface_face_elements,
    compute_region_adjacency,
    compute_region_boundary_adjacency,
    interface_element_definition_summary_rows,
    interface_face_element_summary_rows,
    interface_face_group_summary_rows,
    load_case_spec,
    save_case_spec,
    save_preprocessor_snapshot,
)
from geoai_simkit.runtime import CheckpointManager, RuntimeCompiler
from geoai_simkit.solver.backends import ReferenceBackend


def _parse_bool(text: str) -> bool:
    token = str(text).strip().lower()
    if token in {'1', 'true', 'yes', 'on', 'checked'}:
        return True
    if token in {'0', 'false', 'no', 'off', 'unchecked'}:
        return False
    raise ValueError(f'Expected boolean value, got: {text!r}')


def _add_runtime_options(parser, *, include_device: bool = True, default_profile: str = 'auto', default_device: str | None = None) -> None:
    parser.add_argument('--execution-profile', default=default_profile, choices=['auto', 'cpu-robust', 'cpu-debug', 'gpu'], help='Runtime profile')
    if include_device:
        parser.add_argument('--device', default=default_device, help='Preferred solver device, e.g. cpu or cuda:0')
    parser.add_argument('--partition-count', type=int, default=None, help='Requested runtime partition count')
    parser.add_argument('--communicator', default='local', choices=['local', 'thread', 'mpi'], help='Communicator backend')
    parser.add_argument('--checkpoint-policy', default='stage-and-failure', help='Checkpoint policy label')
    parser.add_argument('--checkpoint-dir', default=None, help='Override checkpoint output directory')
    parser.add_argument('--checkpoint-every', type=int, default=None, help='Write an increment checkpoint every N increments')
    parser.add_argument('--checkpoint-keep-last', type=int, default=None, help='Retain only the latest N checkpoint assets')
    parser.add_argument('--max-cutbacks', type=int, default=None, help='Override increment cutback budget')
    parser.add_argument('--max-stage-retries', type=int, default=None, help='Retry a failed stage from its committed start boundary up to N times')
    parser.add_argument('--resume-checkpoint-id', default=None, help='Resume from a previously written checkpoint id or selector such as latest / latest-stage / latest-failure')
    parser.add_argument('--telemetry-level', default='standard', help='Telemetry verbosity level')
    parser.add_argument('--deterministic', action='store_true', help='Enable deterministic runtime toggles where available')


def _stage_execution_diagnostics_for_case(
    model,
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
) -> dict[str, object]:
    solver = GeneralFEMSolver()
    solver_settings = build_solver_settings(
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
    return dict(solver.backend.stage_execution_diagnostics(model, solver_settings))


def _run_demo(out_dir: Path, *, execution_profile: str = 'auto', device: str | None = None) -> None:
    require_optional_dependency('pyvista', feature='The packaged demo', extra='gui')
    from geoai_simkit.examples.pit_example import run_demo

    out = run_demo(out_dir, execution_profile=execution_profile, device=device)
    print(out)


def _run_gui() -> None:
    require_optional_dependency('PySide6', feature='The desktop GUI', extra='gui')
    require_optional_dependency('pyvista', feature='The desktop GUI', extra='gui')
    require_optional_dependency('pyvistaqt', feature='The desktop GUI', extra='gui')
    from geoai_simkit.app.workbench_window import launch_nextgen_workbench

    launch_nextgen_workbench()


def _export_demo_case(out_path: Path) -> None:
    from geoai_simkit.examples.pit_example import build_demo_case

    path = save_case_spec(build_demo_case(), out_path)
    print(path)


def _prepare_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    payload = {
        'case_name': spec.name,
        'stages': list(prepared.report.generated_stages or [stage.name for stage in prepared.model.stages]),
        'interfaces': list(prepared.report.generated_interfaces),
        'notes': list(prepared.report.notes),
        **dict(prepared.report.metadata),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _inspect_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    point_adjacency_count = len(compute_region_adjacency(prepared.model, min_shared_points=1))
    boundary_adjacency_count = len(compute_region_boundary_adjacency(prepared.model, min_shared_faces=1))
    topology = analyze_interface_topology(prepared.model)
    payload = {
        'case_name': spec.name,
        'geometry_kind': spec.geometry.kind,
        'regions': [str(region.name) for region in prepared.model.region_tags],
        'materials': [str(item.region_name) for item in prepared.model.materials],
        'stages': [stage.name for stage in prepared.model.stages],
        'interfaces': [item.name for item in prepared.model.interfaces],
        'interface_elements': [item.name for item in prepared.model.interface_elements],
        'structures': [item.name for item in prepared.model.structures],
        'boundary_conditions': [str(item.name) for item in prepared.model.boundary_conditions],
        'stage_boundary_condition_count': sum(len(stage.boundary_conditions) for stage in prepared.model.stages),
        'stage_load_count': sum(len(stage.loads) for stage in prepared.model.stages),
        'n_region_adjacencies': point_adjacency_count,
        'n_boundary_adjacencies': boundary_adjacency_count,
        'n_node_split_plans': int(len(topology.split_plans)),
        'n_suggested_duplicate_points': int(topology.metadata.get('n_suggested_duplicate_points', 0)),
        'interface_ready': dict(prepared.model.metadata.get('pipeline.interface_ready') or {}),
        **dict(prepared.report.metadata),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _stage_graph_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    roots = [stage.name for stage in spec.stages if stage.predecessor in {None, ''}]
    payload = {
        'case_name': spec.name,
        'stage_count': len(spec.stages),
        'roots': roots,
        'edges': [
            {'from': stage.predecessor, 'to': stage.name}
            for stage in spec.stages if stage.predecessor not in {None, ''}
        ],
        'stages': [
            {
                'name': stage.name,
                'predecessor': stage.predecessor,
                'activate_regions': list(stage.activate_regions),
                'deactivate_regions': list(stage.deactivate_regions),
                'boundary_condition_count': len(stage.boundary_conditions),
                'load_count': len(stage.loads),
            }
            for stage in spec.stages
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _validate_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    report = AnalysisCaseValidator(spec).validate()
    payload = {
        'ok': bool(report.ok),
        'summary': dict(report.summary),
        'issues': [
            {
                'level': issue.level,
                'code': issue.code,
                'message': issue.message,
                'hint': issue.hint,
                'metadata': dict(issue.metadata),
            }
            for issue in report.issues
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if not report.ok:
        raise SystemExit(1)


def _preprocess_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    artifact = build_preprocessor_snapshot(spec)
    print(json.dumps(artifact.snapshot.to_dict(), indent=2, ensure_ascii=False))


def _export_preprocess(case_path: Path, out_path: Path) -> None:
    spec = load_case_spec(case_path)
    artifact = build_preprocessor_snapshot(spec)
    path = save_preprocessor_snapshot(artifact.snapshot, out_path)
    print(path)


def _plan_case(
    case_path: Path,
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
) -> None:
    spec = load_case_spec(case_path)
    report = AnalysisCaseValidator(spec).validate()
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
    prepared = AnalysisCaseBuilder(spec).build()
    bundle = RuntimeCompiler().compile_case(prepared, plan.compile_config)
    compile_meta = dict(bundle.compile_report.metadata)
    stage_execution_diagnostics = _stage_execution_diagnostics_for_case(
        prepared.model,
        execution_profile=execution_profile,
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
    payload = {
        'case_name': spec.name,
        'geometry_kind': spec.geometry.kind,
        'validation_ok': bool(report.ok),
        'validation_issue_count': len(report.issues),
        'execution_plan': {
            'profile': plan.profile,
            'device': plan.device,
            'has_cuda': plan.has_cuda,
            'thread_count': plan.thread_count,
            'note': plan.note,
            'metadata': dict(plan.metadata),
            'checkpoint': {
                'policy': plan.runtime_config.checkpoint_policy,
                'checkpoint_dir': plan.runtime_config.metadata.get('checkpoint_dir'),
                'checkpoint_every_n_increments': plan.runtime_config.metadata.get('checkpoint_every_n_increments'),
                'checkpoint_keep_last_n': plan.runtime_config.metadata.get('checkpoint_keep_last_n'),
                'resume_checkpoint_id': plan.runtime_config.metadata.get('resume_checkpoint_id'),
            },
            'failure_policy': {
                'rollback_to_stage_start': True,
                'max_cutbacks': plan.runtime_config.metadata.get('max_cutbacks'),
                'max_stage_retries': plan.runtime_config.metadata.get('max_stage_retries'),
            },
        },
        'compile': {
            'partition_count': int(compile_meta.get('partition_count', plan.compile_config.partition_count)),
            'estimated_peak_memory_bytes': int(compile_meta.get('estimated_peak_memory_bytes', 0) or 0),
            'partition_advisory': dict(compile_meta.get('partition_advisory', {}) or {}),
            'stage_execution_diagnostics': stage_execution_diagnostics,
            'stage_partition_diagnostics': list(compile_meta.get('stage_partition_diagnostics', []) or []),
            'stage_linear_system_plans': list(compile_meta.get('stage_linear_system_plans', []) or []),
            'linear_system_partition_estimates': list(compile_meta.get('linear_system_partition_estimates', []) or []),
            'warnings': list(bundle.compile_report.warnings),
            'errors': list(bundle.compile_report.errors),
            'metadata': compile_meta,
        },
        'summary': dict(report.summary),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if not report.ok:
        raise SystemExit(1)


def _partition_case(
    case_path: Path,
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
) -> None:
    spec = load_case_spec(case_path)
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
    prepared = AnalysisCaseBuilder(spec).build()
    bundle = RuntimeCompiler().compile_case(prepared, plan.compile_config)
    compile_meta = dict(bundle.compile_report.metadata)
    stage_execution_diagnostics = _stage_execution_diagnostics_for_case(
        prepared.model,
        execution_profile=execution_profile,
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
    payload = {
        'case_name': spec.name,
        'execution_profile': plan.profile,
        'partition_count': int(compile_meta.get('partition_count', 0) or 0),
        'partition_advisory': dict(compile_meta.get('partition_advisory', {}) or {}),
        'stage_execution_diagnostics': stage_execution_diagnostics,
        'partition_verify_ok': bool(compile_meta.get('partition_verify_ok', False)),
        'partition_verify_issues': list(compile_meta.get('partition_verify_issues', []) or []),
        'halo_reciprocity_ok': bool(compile_meta.get('halo_reciprocity_ok', False)),
        'cells_per_partition': list(compile_meta.get('cells_per_partition', []) or []),
        'gp_states_per_partition': list(compile_meta.get('gp_states_per_partition', []) or []),
        'owned_nodes_per_partition': list(compile_meta.get('owned_nodes_per_partition', []) or []),
        'ghost_nodes_per_partition': list(compile_meta.get('ghost_nodes_per_partition', []) or []),
        'owned_dofs_per_partition': list(compile_meta.get('owned_dofs_per_partition', []) or []),
        'halo_nodes_per_partition': list(compile_meta.get('halo_nodes_per_partition', []) or []),
        'comm_bytes_per_partition': list(compile_meta.get('comm_bytes_per_partition', []) or []),
        'stage_linear_system_plans': list(compile_meta.get('stage_linear_system_plans', []) or []),
        'linear_system_partition_estimates': list(compile_meta.get('linear_system_partition_estimates', []) or []),
        'estimated_comm_bytes_per_increment': int(compile_meta.get('estimated_comm_bytes_per_increment', 0) or 0),
        'halo_node_ratio': float(compile_meta.get('halo_node_ratio', 0.0) or 0.0),
        'partition_summaries': list(compile_meta.get('partition_summaries', []) or []),
        'stage_partition_diagnostics': list(compile_meta.get('stage_partition_diagnostics', []) or []),
        'compile_metadata': compile_meta,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _adjacency_case(case_path: Path, *, min_shared_points: int = 1, mode: str = 'points') -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    mode_key = str(mode or 'points').strip().lower()
    if mode_key == 'faces':
        adjacencies = compute_region_boundary_adjacency(prepared.model, min_shared_faces=max(1, int(min_shared_points)))
    else:
        adjacencies = compute_region_adjacency(prepared.model, min_shared_points=max(1, int(min_shared_points)))
    payload = {
        'case_name': spec.name,
        'adjacency_mode': mode_key,
        'min_shared_points': int(min_shared_points),
        'adjacency_count': len(adjacencies),
        'adjacencies': adjacency_summary_rows(adjacencies),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _topology_case(case_path: Path, *, duplicate_side: str = 'slave') -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    topology = analyze_interface_topology(prepared.model, duplicate_side=duplicate_side)
    print(json.dumps(topology.to_dict(), indent=2, ensure_ascii=False))


def _interface_elements_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    faces = compute_interface_face_elements(prepared.model)
    payload = {
        'case_name': spec.name,
        'geometry_kind': spec.geometry.kind,
        'summary': dict(prepared.report.metadata),
        'interface_face_groups': interface_face_group_summary_rows(faces.groups),
        'interface_face_elements': interface_face_element_summary_rows(faces.elements),
        'metadata': dict(faces.metadata),
        'interface_ready': dict(prepared.model.metadata.get('pipeline.interface_ready') or {}),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _export_interface_elements(case_path: Path, out_path: Path) -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    payload = {
        'case_name': spec.name,
        'geometry_kind': spec.geometry.kind,
        'summary': dict(prepared.report.metadata),
        'interface_elements': interface_element_definition_summary_rows(prepared.model.interface_elements),
        'interface_ready': dict(prepared.model.metadata.get('pipeline.interface_ready') or {}),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(out_path)


def _interface_ready_case(case_path: Path) -> None:
    spec = load_case_spec(case_path)
    prepared = AnalysisCaseBuilder(spec).build()
    payload = {
        'case_name': spec.name,
        'geometry_kind': spec.geometry.kind,
        'interface_ready': dict(prepared.model.metadata.get('pipeline.interface_ready') or {}),
        'summary': dict(prepared.report.metadata),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _checkpoint_list(checkpoint_dir: Path) -> None:
    manager = CheckpointManager(checkpoint_dir)
    checkpoint_ids = manager.list_checkpoint_ids()
    checkpoints = [manager.describe_checkpoint(checkpoint_id) for checkpoint_id in checkpoint_ids]
    checkpoint_kind_counts: dict[str, int] = {}
    for item in checkpoints:
        checkpoint_kind = str(item.get('kind', 'unknown'))
        checkpoint_kind_counts[checkpoint_kind] = int(checkpoint_kind_counts.get(checkpoint_kind, 0)) + 1
    payload = {
        'checkpoint_dir': str(checkpoint_dir),
        'checkpoint_count': len(checkpoint_ids),
        'checkpoint_ids': list(checkpoint_ids),
        'checkpoint_kind_counts': checkpoint_kind_counts,
        'latest_checkpoint_ids': manager.latest_checkpoint_ids(),
        'checkpoints': checkpoints,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _checkpoint_show(checkpoint_dir: Path, checkpoint_id: str) -> None:
    manager = CheckpointManager(checkpoint_dir)
    payload = manager.describe_checkpoint(checkpoint_id)
    payload['checkpoint_dir'] = str(checkpoint_dir)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _checkpoint_validate(checkpoint_dir: Path, checkpoint_id: str = 'latest') -> None:
    manager = CheckpointManager(checkpoint_dir)
    payload = manager.validate_checkpoint(checkpoint_id)
    payload['checkpoint_dir'] = str(checkpoint_dir)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _stage_field_arrays(result_db) -> dict[str, dict[str, dict[str, object]]]:
    stage_map: dict[str, dict[str, dict[str, object]]] = {}
    for field in getattr(result_db, 'fields', ()) or ():
        stage_name = None if field.stage in {None, '', '__global__'} else str(field.stage)
        if stage_name is None:
            continue
        stage_map.setdefault(stage_name, {})[str(field.name)] = {
            'association': str(field.association),
            'shape': list(np.asarray(field.values).shape),
            'values': np.asarray(field.values, dtype=float),
        }
    return stage_map


def _compare_result_databases(left_db, right_db, *, abs_tol: float, rel_tol: float) -> dict[str, object]:
    left_stage_map = _stage_field_arrays(left_db)
    right_stage_map = _stage_field_arrays(right_db)
    stage_names: list[str] = []
    for stage_name in [*left_stage_map.keys(), *right_stage_map.keys()]:
        if stage_name not in stage_names:
            stage_names.append(stage_name)

    field_differences: list[dict[str, object]] = []
    missing_fields: list[dict[str, object]] = []
    shape_mismatches: list[dict[str, object]] = []
    overall_ok = True
    overall_max_abs_diff = 0.0
    overall_max_rel_l2_diff = 0.0

    for stage_name in stage_names:
        left_fields = left_stage_map.get(stage_name, {})
        right_fields = right_stage_map.get(stage_name, {})
        field_names: list[str] = []
        for field_name in [*left_fields.keys(), *right_fields.keys()]:
            if field_name not in field_names:
                field_names.append(field_name)
        for field_name in field_names:
            left_entry = left_fields.get(field_name)
            right_entry = right_fields.get(field_name)
            if left_entry is None or right_entry is None:
                overall_ok = False
                missing_fields.append(
                    {
                        'stage_name': stage_name,
                        'field_name': field_name,
                        'missing_in': 'baseline' if left_entry is None else 'candidate',
                    }
                )
                continue
            if list(left_entry['shape']) != list(right_entry['shape']):
                overall_ok = False
                shape_mismatches.append(
                    {
                        'stage_name': stage_name,
                        'field_name': field_name,
                        'baseline_shape': list(left_entry['shape']),
                        'candidate_shape': list(right_entry['shape']),
                    }
                )
                continue
            left_values = np.asarray(left_entry['values'], dtype=float)
            right_values = np.asarray(right_entry['values'], dtype=float)
            diff = left_values - right_values
            max_abs_diff = float(np.max(np.abs(diff))) if diff.size else 0.0
            l2_diff = float(np.linalg.norm(diff.reshape(-1))) if diff.size else 0.0
            ref_l2_norm = float(np.linalg.norm(left_values.reshape(-1))) if left_values.size else 0.0
            rel_l2_diff = float(l2_diff / max(1.0e-12, ref_l2_norm))
            field_ok = bool(np.allclose(left_values, right_values, rtol=rel_tol, atol=abs_tol))
            overall_ok = overall_ok and field_ok
            overall_max_abs_diff = max(overall_max_abs_diff, max_abs_diff)
            overall_max_rel_l2_diff = max(overall_max_rel_l2_diff, rel_l2_diff)
            field_differences.append(
                {
                    'stage_name': stage_name,
                    'field_name': field_name,
                    'association': str(left_entry['association']),
                    'shape': list(left_entry['shape']),
                    'max_abs_diff': max_abs_diff,
                    'l2_diff': l2_diff,
                    'rel_l2_diff': rel_l2_diff,
                    'ok': field_ok,
                }
            )

    return {
        'ok': bool(overall_ok),
        'stage_count': len(stage_names),
        'field_count': len(field_differences),
        'abs_tol': float(abs_tol),
        'rel_tol': float(rel_tol),
        'max_abs_diff': float(overall_max_abs_diff),
        'max_rel_l2_diff': float(overall_max_rel_l2_diff),
        'missing_fields': missing_fields,
        'shape_mismatches': shape_mismatches,
        'field_differences': field_differences,
    }


def _stage_linear_system_diagnostics_map(result_db) -> dict[str, dict[str, object]]:
    stage_map: dict[str, dict[str, object]] = {}
    for record in getattr(result_db, 'stages', ()) or ():
        stage_map[str(record.stage_name)] = dict(record.metadata.get('linear_system_diagnostics', {}) or {})
    return stage_map


def _compare_linear_system_diagnostics(left_db, right_db) -> dict[str, object]:
    left_map = _stage_linear_system_diagnostics_map(left_db)
    right_map = _stage_linear_system_diagnostics_map(right_db)
    stage_names: list[str] = []
    for stage_name in [*left_map.keys(), *right_map.keys()]:
        if stage_name not in stage_names:
            stage_names.append(stage_name)

    missing_stage_names: list[str] = []
    mismatch_stage_names: list[str] = []
    stage_rows: list[dict[str, object]] = []
    ok = True
    for stage_name in stage_names:
        left = dict(left_map.get(stage_name, {}) or {})
        right = dict(right_map.get(stage_name, {}) or {})
        if not left or not right:
            ok = False
            missing_stage_names.append(stage_name)
            stage_rows.append(
                {
                    'stage_name': stage_name,
                    'ok': False,
                    'missing_in': 'baseline' if not left else 'candidate',
                }
            )
            continue
        stage_ok = all(
            (
                bool(left.get('has_actual_operator_summary', False))
                == bool(right.get('has_actual_operator_summary', False)),
                int(left.get('actual_active_cell_count', 0) or 0)
                == int(right.get('actual_active_cell_count', 0) or 0),
                list(left.get('actual_matrix_shape', []) or [])
                == list(right.get('actual_matrix_shape', []) or []),
                int(left.get('actual_matrix_storage_bytes', 0) or 0)
                == int(right.get('actual_matrix_storage_bytes', 0) or 0),
                int(left.get('actual_global_rhs_size', 0) or 0)
                == int(right.get('actual_global_rhs_size', 0) or 0),
                bool(left.get('global_plan_vs_actual_ok', False))
                == bool(right.get('global_plan_vs_actual_ok', False)),
            )
        )
        if not stage_ok:
            ok = False
            mismatch_stage_names.append(stage_name)
        stage_rows.append(
            {
                'stage_name': stage_name,
                'ok': bool(stage_ok),
                'baseline_has_actual_operator_summary': bool(
                    left.get('has_actual_operator_summary', False)
                ),
                'candidate_has_actual_operator_summary': bool(
                    right.get('has_actual_operator_summary', False)
                ),
                'baseline_actual_active_cell_count': int(
                    left.get('actual_active_cell_count', 0) or 0
                ),
                'candidate_actual_active_cell_count': int(
                    right.get('actual_active_cell_count', 0) or 0
                ),
                'baseline_actual_matrix_shape': list(left.get('actual_matrix_shape', []) or []),
                'candidate_actual_matrix_shape': list(
                    right.get('actual_matrix_shape', []) or []
                ),
                'baseline_actual_matrix_storage_bytes': int(
                    left.get('actual_matrix_storage_bytes', 0) or 0
                ),
                'candidate_actual_matrix_storage_bytes': int(
                    right.get('actual_matrix_storage_bytes', 0) or 0
                ),
                'baseline_actual_global_rhs_size': int(
                    left.get('actual_global_rhs_size', 0) or 0
                ),
                'candidate_actual_global_rhs_size': int(
                    right.get('actual_global_rhs_size', 0) or 0
                ),
                'baseline_actual_partition_rhs_size_total': int(
                    left.get('actual_partition_rhs_size_total', 0) or 0
                ),
                'candidate_actual_partition_rhs_size_total': int(
                    right.get('actual_partition_rhs_size_total', 0) or 0
                ),
                'baseline_consistency_level': str(
                    left.get('consistency_level', 'estimated-only')
                ),
                'candidate_consistency_level': str(
                    right.get('consistency_level', 'estimated-only')
                ),
            }
        )
    return {
        'ok': bool(ok),
        'stage_count': int(len(stage_names)),
        'missing_stage_names': missing_stage_names,
        'mismatch_stage_names': mismatch_stage_names,
        'stages': stage_rows,
        'baseline_summary': dict(left_db.metadata.get('linear_system_diagnostics_summary', {}) or {}),
        'candidate_summary': dict(
            right_db.metadata.get('linear_system_diagnostics_summary', {}) or {}
        ),
    }


def _compile_summary(bundle) -> dict[str, object]:
    meta = dict(bundle.compile_report.metadata)
    return {
        'partition_count': int(meta.get('partition_count', 0) or 0),
        'stage_count': int(meta.get('stage_count', 0) or 0),
        'partition_verify_ok': bool(meta.get('partition_verify_ok', False)),
        'partition_balance_ratio': float(meta.get('partition_balance_ratio', 1.0) or 1.0),
        'node_balance_ratio': float(meta.get('node_balance_ratio', 1.0) or 1.0),
        'dof_balance_ratio': float(meta.get('dof_balance_ratio', 1.0) or 1.0),
        'halo_node_ratio': float(meta.get('halo_node_ratio', 0.0) or 0.0),
        'estimated_peak_memory_bytes': int(meta.get('estimated_peak_memory_bytes', 0) or 0),
        'cells_per_partition': list(meta.get('cells_per_partition', []) or []),
        'owned_dofs_per_partition': list(meta.get('owned_dofs_per_partition', []) or []),
        'comm_bytes_per_partition': list(meta.get('comm_bytes_per_partition', []) or []),
        'stage_partition_diagnostics': list(meta.get('stage_partition_diagnostics', []) or []),
        'stage_linear_system_plans': list(meta.get('stage_linear_system_plans', []) or []),
        'linear_system_partition_estimates': list(meta.get('linear_system_partition_estimates', []) or []),
        'partition_advisory': dict(meta.get('partition_advisory', {}) or {}),
        'warnings': list(bundle.compile_report.warnings),
        'errors': list(bundle.compile_report.errors),
    }


def _reference_runtime_assembly_summary(result) -> dict[str, object]:
    solved_model = getattr(result, 'solved_model', None)
    if solved_model is None:
        return {}
    assembly_meta = dict(getattr(solved_model, 'metadata', {}).get('linear_element_assembly', {}) or {})
    return {
        str(stage_name): dict(stage_meta)
        for stage_name, stage_meta in assembly_meta.items()
    }


def _stage_report_summary(runtime_report) -> list[dict[str, object]]:
    if runtime_report is None:
        return []
    rows: list[dict[str, object]] = []
    for report in runtime_report.stage_reports:
        rows.append(
            {
                'stage_name': str(report.stage_name),
                'status': str(report.status),
                'ok': bool(report.ok),
                'active_cell_count': int(report.active_cell_count),
                'active_region_count': int(report.active_region_count),
                'increment_count': int(report.increment_count),
                'iteration_count': int(report.iteration_count),
                'field_names': list(report.field_names),
                'checkpoint_id': report.checkpoint_id,
                'stage_retry_count': int(report.metadata.get('stage_retry_count', 0) or 0),
                'cutback_count': int(report.metadata.get('cutback_count', 0) or 0),
                'accepted_increment_count': int(report.metadata.get('accepted_increment_count', 0) or 0),
                'execution_path': report.metadata.get('execution_path'),
                'assembly_info': dict(report.metadata.get('assembly_info', {}) or {}),
                'linear_system_diagnostics': dict(
                    report.metadata.get('linear_system_diagnostics', {}) or {}
                ),
            }
        )
    return rows


def _compare_partitions_case(
    case_path: Path,
    *,
    execution_profile: str = 'cpu-robust',
    partition_count: int = 2,
    abs_tol: float = 1.0e-8,
    rel_tol: float = 1.0e-8,
) -> None:
    spec = load_case_spec(case_path)
    candidate_partition_count = max(2, int(partition_count or 2))
    backend = ReferenceBackend()
    support_settings = build_solver_settings(
        execution_profile,
        device='cpu',
        partition_count=1,
        checkpoint_policy='none',
    )
    prepared = AnalysisCaseBuilder(spec).build()
    if not backend.supports_stage_execution(prepared.model, support_settings):
        raise RuntimeError(
            'compare-partitions-case 目前只支持重建后的线性连续体 stage runtime 主链路；'
            '包含结构/接口/非线性材料的案例仍需先走回退路径。'
        )

    solver = GeneralFEMSolver(backend=backend)
    with tempfile.TemporaryDirectory(prefix='geoai-simkit-compare-') as tmp_dir:
        temp_root = Path(tmp_dir)
        base_plan = build_execution_plan(
            execution_profile,
            device='cpu',
            partition_count=1,
            checkpoint_policy='none',
            checkpoint_dir=str(temp_root / 'p1_checkpoints'),
        )
        candidate_plan = build_execution_plan(
            execution_profile,
            device='cpu',
            partition_count=candidate_partition_count,
            checkpoint_policy='none',
            checkpoint_dir=str(temp_root / f'p{candidate_partition_count}_checkpoints'),
        )
        base_result = solver.run_task(
            AnalysisTaskSpec(
                case=spec,
                execution_profile=execution_profile,
                device='cpu',
                compile_config=base_plan.compile_config,
                runtime_config=base_plan.runtime_config,
            )
        )
        candidate_result = solver.run_task(
            AnalysisTaskSpec(
                case=spec,
                execution_profile=execution_profile,
                device='cpu',
                compile_config=candidate_plan.compile_config,
                runtime_config=candidate_plan.runtime_config,
            )
        )

    if base_result.result_db is None or candidate_result.result_db is None:
        raise RuntimeError('Partition comparison requires runtime result databases from both runs.')

    comparison = _compare_result_databases(
        base_result.result_db,
        candidate_result.result_db,
        abs_tol=float(abs_tol),
        rel_tol=float(rel_tol),
    )
    linear_system_comparison = _compare_linear_system_diagnostics(
        base_result.result_db,
        candidate_result.result_db,
    )
    payload = {
        'case_name': spec.name,
        'execution_profile': execution_profile,
        'backend': 'reference-linear-stage-runtime',
        'baseline_partition_count': 1,
        'candidate_partition_count': int(candidate_partition_count),
        'baseline_stage_names': list(base_result.result_db.stage_names()),
        'candidate_stage_names': list(candidate_result.result_db.stage_names()),
        'compile': {
            'baseline': _compile_summary(base_result.compilation_bundle),
            'candidate': _compile_summary(candidate_result.compilation_bundle),
        },
        'runtime_assembly': {
            'baseline': _reference_runtime_assembly_summary(base_result),
            'candidate': _reference_runtime_assembly_summary(candidate_result),
        },
        'linear_system_comparison': linear_system_comparison,
        'comparison': comparison,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _document_to_payload(document) -> dict:
    return {
        'case_name': document.case.name,
        'mode': document.mode,
        'dirty': document.dirty,
        'browser': {
            'model_name': document.browser.model_name,
            'geometry_state': document.browser.geometry_state,
            'block_names': [item.name for item in document.browser.blocks],
            'blocks': [
                {
                    'name': item.name,
                    'material_name': item.material_name,
                    'visible': item.visible,
                    'locked': item.locked,
                    'active_stages': list(item.active_stages),
                }
                for item in document.browser.blocks
            ],
            'stage_names': [item.name for item in document.browser.stage_rows],
            'stages': [
                {
                    'name': item.name,
                    'predecessor': item.predecessor,
                    'activate_regions': list(item.activate_regions),
                    'deactivate_regions': list(item.deactivate_regions),
                    'boundary_condition_count': item.boundary_condition_count,
                    'load_count': item.load_count,
                }
                for item in document.browser.stage_rows
            ],
            'object_count': document.browser.object_count,
            'interface_count': document.browser.interface_count,
            'interface_element_count': document.browser.interface_element_count,
            'structure_count': document.browser.structure_count,
        },
        'preprocess': None if document.preprocess is None else {
            'n_region_surfaces': document.preprocess.n_region_surfaces,
            'n_region_adjacencies': document.preprocess.n_region_adjacencies,
            'n_boundary_adjacencies': document.preprocess.n_boundary_adjacencies,
            'n_interface_candidates': document.preprocess.n_interface_candidates,
            'n_node_split_plans': document.preprocess.n_node_split_plans,
            'n_interface_elements': document.preprocess.n_interface_elements,
        },
        'validation': None if document.validation is None else {
            'ok': document.validation.ok,
            'error_count': document.validation.error_count,
            'warning_count': document.validation.warning_count,
            'info_count': document.validation.info_count,
            'summary': dict(document.validation.summary),
            'issues': list(document.validation.issues),
        },
        'results': None if document.results is None else {
            'stage_count': document.results.stage_count,
            'field_count': document.results.field_count,
            'field_labels': list(document.results.field_labels),
            'stage_asset_count': int(document.results.metadata.get('stage_asset_count', 0) or 0),
            'stage_linear_system_plan_count': int(document.results.metadata.get('stage_linear_system_plan_count', 0) or 0),
            'stage_linear_system_diagnostics_count': int(
                document.results.metadata.get('stage_linear_system_diagnostics_count', 0) or 0
            ),
            'linear_system_diagnostics_summary': dict(
                document.results.metadata.get('linear_system_diagnostics_summary', {}) or {}
            ),
            'stage_metadata': (
                []
                if document.result_db is None
                else [
                    {
                        'stage_name': record.stage_name,
                        'field_count': len(record.fields),
                        'has_stage_asset': bool(record.metadata.get('stage_asset')),
                        'has_linear_system_diagnostics': bool(
                            record.metadata.get('linear_system_diagnostics')
                        ),
                        'active_partition_count': (
                            record.metadata.get('stage_summary', {}) or {}
                        ).get('active_partition_count'),
                        'active_cell_count_match': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('active_cell_count_match'),
                        'linear_system_consistency_level': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('consistency_level'),
                        'linear_system_ok': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('ok'),
                        'actual_global_dof_count': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_global_dof_count'),
                        'actual_global_rhs_size': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_global_rhs_size'),
                        'actual_global_rhs_norm': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_global_rhs_norm'),
                        'actual_global_residual_norm': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_global_residual_norm'),
                        'actual_global_reaction_norm': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_global_reaction_norm'),
                        'actual_partition_rhs_size_total': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_partition_rhs_size_total'),
                        'actual_partition_rhs_norm_sum': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_partition_rhs_norm_sum'),
                        'actual_partition_residual_norm_sum': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_partition_residual_norm_sum'),
                        'actual_partition_reaction_norm_sum': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_partition_reaction_norm_sum'),
                        'estimated_matrix_storage_bytes': (
                            record.metadata.get('stage_linear_system_plan', {}) or {}
                        ).get('estimated_matrix_storage_bytes'),
                        'actual_matrix_storage_bytes': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('actual_matrix_storage_bytes'),
                        'matrix_storage_ratio_actual_to_estimated': (
                            record.metadata.get('linear_system_diagnostics', {}) or {}
                        ).get('matrix_storage_ratio_actual_to_estimated'),
                    }
                    for record in document.result_db.stages
                ]
            ),
        },
        'job_plan': None if document.job_plan is None else {
            'profile': document.job_plan.profile,
            'device': document.job_plan.device,
            'thread_count': document.job_plan.thread_count,
            'has_cuda': document.job_plan.has_cuda,
            'note': document.job_plan.note,
            'estimated_partitions': document.job_plan.estimated_partitions,
            'estimated_peak_memory_bytes': document.job_plan.estimated_peak_memory_bytes,
            'partition_advisory': dict(document.job_plan.partition_advisory),
            'stage_execution_diagnostics': dict(document.job_plan.stage_execution_diagnostics),
        },
        'compile_report': document.compile_report,
        'partition_advisory': dict((document.compile_report or {}).get('partition_advisory', {}) or {}),
        'stage_execution_diagnostics': dict(document.metadata.get('stage_execution_diagnostics', {}) or {}),
        'runtime_metadata': dict(document.metadata.get('runtime_metadata', {}) or {}),
        'runtime_manifest_path': document.metadata.get('runtime_manifest_path'),
        'telemetry_summary': dict(document.telemetry_summary),
        'checkpoint_ids': list(document.checkpoint_ids),
        'increment_checkpoint_ids': list(document.increment_checkpoint_ids),
        'failure_checkpoint_ids': list(document.failure_checkpoint_ids),
        'messages': list(document.messages),
    }


def _workbench_case(case_path: Path) -> None:
    document = WorkbenchService().load_document(case_path, mode='geometry')
    print(json.dumps(_document_to_payload(document), indent=2, ensure_ascii=False))




def _workbench_validate_case(case_path: Path) -> None:
    document = WorkbenchService().load_document(case_path, mode='geometry')
    payload = {
        'case_name': document.case.name,
        'validation': None if document.validation is None else {
            'ok': document.validation.ok,
            'error_count': document.validation.error_count,
            'warning_count': document.validation.warning_count,
            'info_count': document.validation.info_count,
            'summary': dict(document.validation.summary),
            'issues': list(document.validation.issues),
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

def _apply_workbench_edits(document, args) -> None:
    service = WorkbenchService()
    for spec in args.set_material or []:
        region_name, material_name = spec.split('=', 1)
        service.set_block_material(document, region_name.strip(), material_name.strip())
    for spec in args.set_visibility or []:
        region_name, value = spec.split('=', 1)
        service.set_block_flags(document, region_name.strip(), visible=_parse_bool(value))
    for spec in args.set_locked or []:
        region_name, value = spec.split('=', 1)
        service.set_block_flags(document, region_name.strip(), locked=_parse_bool(value))
    for stage_name in args.add_stage or []:
        service.add_stage(document, stage_name.strip(), copy_from=document.browser.stage_rows[-1].name if document.browser.stage_rows else None)
        document = service.refresh_document(document, preserve_results=True)
    for spec in args.clone_stage or []:
        source_name, new_name = spec.split(':', 1)
        service.clone_stage(document, source_name.strip(), new_name.strip())
        document = service.refresh_document(document, preserve_results=True)
    for spec in args.set_stage_active or []:
        head, value = spec.split('=', 1)
        stage_name, region_name = head.split(':', 1)
        service.set_stage_region_state(document, stage_name.strip(), region_name.strip(), _parse_bool(value))
    for spec in args.set_predecessor or []:
        stage_name, predecessor = spec.split('=', 1)
        predecessor_value = predecessor.strip()
        if predecessor_value.lower() in {'', 'none', '<root>', 'root'}:
            predecessor_value = None
        service.set_stage_predecessor(document, stage_name.strip(), predecessor_value)
    if args.mesh_size is not None:
        service.set_mesh_global_size(document, float(args.mesh_size))
    return document


def _workbench_edit_case(case_path: Path, out_path: Path, args) -> None:
    service = WorkbenchService()
    document = service.load_document(case_path, mode='geometry')
    document = _apply_workbench_edits(document, args)
    document = service.refresh_document(document, preserve_results=True)
    saved = service.save_document(document, out_path)
    payload = _document_to_payload(document)
    payload['saved_to'] = str(saved)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _workbench_run_case(
    case_path: Path,
    out_dir: Path,
    *,
    execution_profile: str = 'cpu-robust',
    device: str | None = 'cpu',
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
) -> None:
    service = WorkbenchService()
    document = service.load_document(case_path, mode='solve')
    plan = service.plan_document(document, execution_profile=execution_profile, device=device, partition_count=partition_count, communicator_backend=communicator_backend, checkpoint_policy=checkpoint_policy, checkpoint_dir=checkpoint_dir, checkpoint_every_n_increments=checkpoint_every_n_increments, checkpoint_keep_last_n=checkpoint_keep_last_n, max_cutbacks=max_cutbacks, max_stage_retries=max_stage_retries, telemetry_level=telemetry_level, deterministic=deterministic, resume_checkpoint_id=resume_checkpoint_id)
    run = service.run_document(document, out_dir, execution_profile=execution_profile, device=device, export_stage_series=False, partition_count=partition_count, communicator_backend=communicator_backend, checkpoint_policy=checkpoint_policy, checkpoint_dir=checkpoint_dir, checkpoint_every_n_increments=checkpoint_every_n_increments, checkpoint_keep_last_n=checkpoint_keep_last_n, max_cutbacks=max_cutbacks, max_stage_retries=max_stage_retries, telemetry_level=telemetry_level, deterministic=deterministic, resume_checkpoint_id=resume_checkpoint_id)
    payload = _document_to_payload(document)
    payload['run'] = {
        'profile': plan.profile,
        'device': plan.device,
        'out_path': str(run.out_path) if run.out_path is not None else None,
        'runtime_manifest_path': (
            None
            if run.runtime_manifest_path is None
            else str(run.runtime_manifest_path)
        ),
        'result_stage_count': run.stage_count,
        'result_field_count': run.field_count,
        'partition_advisory': dict(run.partition_advisory),
        'runtime_metadata': dict(run.runtime_metadata),
        'stage_asset_count': int(run.runtime_metadata.get('stage_asset_count', 0) or 0),
        'stage_linear_system_diagnostics_count': int(
            run.runtime_metadata.get('stage_linear_system_diagnostics_count', 0) or 0
        ),
        'linear_system_diagnostics_summary': dict(
            run.runtime_metadata.get('linear_system_diagnostics_summary', {}) or {}
        ),
        'checkpoint_ids': list(run.checkpoint_ids),
        'increment_checkpoint_ids': list(run.increment_checkpoint_ids),
        'failure_checkpoint_ids': list(run.failure_checkpoint_ids),
        'telemetry_summary': dict(run.telemetry_summary),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _run_case(
    case_path: Path,
    out_dir: Path,
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
) -> None:
    spec = load_case_spec(case_path)
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
    result = GeneralFEMSolver().run_task(
        AnalysisTaskSpec(
            case=spec,
            execution_profile=execution_profile,
            device=device,
            compile_config=plan.compile_config,
            runtime_config=plan.runtime_config,
            export=AnalysisExportSpec(out_dir=out_dir, stem=spec.name),
        )
    )
    runtime_report = result.runtime_report
    payload = {
        'case_name': spec.name,
        'execution_profile': execution_profile,
        'device': plan.device,
        'out_path': str(out_dir / f'{spec.name}.vtu'),
        'runtime_manifest_path': str(out_dir / f'{spec.name}_runtime_manifest.json'),
        'compile': _compile_summary(result.compilation_bundle),
        'runtime': {
            'ok': bool(runtime_report.ok) if runtime_report is not None else False,
            'execution_mode': None if runtime_report is None else runtime_report.metadata.get('execution_mode'),
            'partition_count': None if runtime_report is None else runtime_report.metadata.get('partition_count'),
            'checkpoint_dir': None if runtime_report is None else runtime_report.metadata.get('checkpoint_dir'),
            'checkpoint_policy': {} if runtime_report is None else dict(runtime_report.metadata.get('checkpoint_policy', {}) or {}),
            'failure_policy': {} if runtime_report is None else dict(runtime_report.metadata.get('failure_policy', {}) or {}),
            'telemetry_summary': dict(result.metadata.get('telemetry_summary', {}) or {}),
            'checkpoint_ids': list(result.metadata.get('checkpoint_ids', ()) or ()),
            'increment_checkpoint_ids': list(result.metadata.get('increment_checkpoint_ids', ()) or ()),
            'failure_checkpoint_ids': list(result.metadata.get('failure_checkpoint_ids', ()) or ()),
            'resume_checkpoint_selector': None if runtime_report is None else runtime_report.metadata.get('resume_checkpoint_selector'),
            'resumed_from_checkpoint': None if runtime_report is None else runtime_report.metadata.get('resumed_from_checkpoint'),
            'resume_checkpoint_kind': None if runtime_report is None else runtime_report.metadata.get('resume_checkpoint_kind'),
            'resume_checkpoint_validation': {} if runtime_report is None else dict(runtime_report.metadata.get('resume_checkpoint_validation', {}) or {}),
            'partition_advisory': {} if runtime_report is None else dict(runtime_report.metadata.get('partition_advisory', {}) or {}),
            'stage_execution_diagnostics': {} if runtime_report is None else dict(runtime_report.metadata.get('stage_execution_diagnostics', {}) or {}),
            'stage_asset_count': 0 if runtime_report is None else int(runtime_report.metadata.get('stage_asset_count', 0) or 0),
            'stage_linear_system_diagnostics_count': 0 if runtime_report is None else int(runtime_report.metadata.get('stage_linear_system_diagnostics_count', 0) or 0),
            'stage_linear_system_plans': [] if runtime_report is None else list(runtime_report.metadata.get('stage_linear_system_plans', []) or []),
            'linear_system_partition_estimates': [] if runtime_report is None else list(runtime_report.metadata.get('linear_system_partition_estimates', []) or []),
            'linear_system_diagnostics_summary': {} if runtime_report is None else dict(runtime_report.metadata.get('linear_system_diagnostics_summary', {}) or {}),
            'last_reduction_summary': {} if runtime_report is None else dict(runtime_report.metadata.get('last_reduction_summary', {}) or {}),
            'stage_reports': _stage_report_summary(runtime_report),
        },
        'runtime_assembly': _reference_runtime_assembly_summary(result),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='geoai-simkit', description='Geotechnical simulation starter toolkit')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check-env', help='Show optional dependency availability')
    demo = sub.add_parser('demo', help='Run the packaged pit demo')
    demo.add_argument('--out-dir', default='exports', help='Directory for exported demo files')
    demo.add_argument('--execution-profile', default='auto', choices=['auto', 'cpu-robust', 'cpu-debug', 'gpu'], help='Demo runtime profile')
    demo.add_argument('--device', default=None, help='Preferred solver device, e.g. cpu or cuda:0')
    export_case = sub.add_parser('export-demo-case', help='Export the packaged demo as a portable case file')
    export_case.add_argument('--out', default='pit_demo_case.json', help='Output case path (.json or .yaml)')
    prep = sub.add_parser('prepare-case', help='Load and prepare a portable case file without solving')
    prep.add_argument('case_path', help='Path to a JSON or YAML case file')
    inspect_case = sub.add_parser('inspect-case', help='Prepare a portable case file and summarize regions/materials/stages')
    inspect_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    stage_graph = sub.add_parser('stage-graph-case', help='Summarize the case stage graph and predecessor edges')
    stage_graph.add_argument('case_path', help='Path to a JSON or YAML case file')
    preprocess_case = sub.add_parser('preprocess-case', help='Build a preprocessor snapshot with surfaces, adjacencies, interface candidates, and node-split suggestions')
    preprocess_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    export_preprocess = sub.add_parser('export-preprocess', help='Write a preprocessor snapshot to JSON or YAML')
    export_preprocess.add_argument('case_path', help='Path to a JSON or YAML case file')
    export_preprocess.add_argument('--out', default='preprocess_snapshot.json', help='Output path (.json or .yaml)')
    adjacency_case = sub.add_parser('adjacency-case', help='Prepare a portable case file and summarize region adjacencies')
    adjacency_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    adjacency_case.add_argument('--min-shared-points', type=int, default=1, help='Minimum shared point/face count for reporting adjacency pairs')
    adjacency_case.add_argument('--mode', default='points', choices=['points', 'faces'], help='Adjacency analysis mode')
    topology_case = sub.add_parser('topology-case', help='Prepare a portable case file and summarize interface topology / node-split suggestions')
    topology_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    topology_case.add_argument('--duplicate-side', default='slave', choices=['slave', 'master'], help='Which interface side should be duplicated in the split plan')
    interface_ready_case = sub.add_parser('interface-ready-case', help='Prepare a portable case file and summarize automatic interface-ready preprocessing')
    interface_ready_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    interface_elements_case = sub.add_parser('interface-elements-case', help='Prepare a portable case file and summarize explicit face-aware interface topology preview elements')
    interface_elements_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    export_interface_elements = sub.add_parser('export-interface-elements', help='Write explicit interface element definitions to JSON')
    export_interface_elements.add_argument('case_path', help='Path to a JSON or YAML case file')
    export_interface_elements.add_argument('--out', default='interface_elements.json', help='Output JSON path')
    validate_case = sub.add_parser('validate-case', help='Validate a portable case file and return structured issues')
    validate_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    plan_case = sub.add_parser('plan-case', help='Validate a portable case and show the execution plan that would be used')
    plan_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    _add_runtime_options(plan_case)
    partition_case = sub.add_parser('partition-case', help='Compile a portable case and show partition / halo diagnostics')
    partition_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    _add_runtime_options(partition_case)
    compare_partitions = sub.add_parser('compare-partitions-case', help='Run the rebuilt linear-continuum reference runtime with 1 vs N partitions and compare stage results')
    compare_partitions.add_argument('case_path', help='Path to a JSON or YAML case file')
    compare_partitions.add_argument('--execution-profile', default='cpu-robust', choices=['cpu-robust', 'cpu-debug'], help='Reference runtime profile')
    compare_partitions.add_argument('--partition-count', type=int, default=2, help='Candidate partition count to compare against the 1-partition baseline')
    compare_partitions.add_argument('--abs-tol', type=float, default=1.0e-8, help='Absolute tolerance for stage field comparisons')
    compare_partitions.add_argument('--rel-tol', type=float, default=1.0e-8, help='Relative tolerance for stage field comparisons')
    run_case = sub.add_parser('run-case', help='Solve a portable case file and export VTU results')
    run_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    run_case.add_argument('--out-dir', default='exports', help='Directory for exported case files')
    _add_runtime_options(run_case)
    checkpoint_list = sub.add_parser('checkpoint-list', help='List checkpoint assets in a runtime checkpoint directory')
    checkpoint_list.add_argument('checkpoint_dir', help='Runtime checkpoint directory')
    checkpoint_show = sub.add_parser('checkpoint-show', help='Show one checkpoint asset summary')
    checkpoint_show.add_argument('checkpoint_dir', help='Runtime checkpoint directory')
    checkpoint_show.add_argument('checkpoint_id', help='Checkpoint id such as stage-000 or failure-001-0001')
    checkpoint_validate = sub.add_parser('checkpoint-validate', help='Validate one checkpoint asset and report restart contract issues')
    checkpoint_validate.add_argument('checkpoint_dir', help='Runtime checkpoint directory')
    checkpoint_validate.add_argument('checkpoint_id', nargs='?', default='latest', help='Checkpoint id or selector such as latest, latest-stage, or latest-failure')
    sub.add_parser('gui', help='Launch the next-generation Qt/PyVista workbench')
    workbench_case = sub.add_parser('workbench-case', help='Prepare a portable case and summarize next-generation browser/preprocess state')
    workbench_case.add_argument('case_path', help='Path to a JSON or YAML case file')
    workbench_edit = sub.add_parser('workbench-edit-case', help='Apply next-generation workbench edits and save the updated case file')
    workbench_edit.add_argument('case_path', help='Path to a JSON or YAML case file')
    workbench_edit.add_argument('--out', required=True, help='Where to write the edited case')
    workbench_edit.add_argument('--set-material', action='append', default=[], metavar='REGION=MATERIAL')
    workbench_edit.add_argument('--set-visibility', action='append', default=[], metavar='REGION=BOOL')
    workbench_edit.add_argument('--set-locked', action='append', default=[], metavar='REGION=BOOL')
    workbench_edit.add_argument('--set-stage-active', action='append', default=[], metavar='STAGE:REGION=BOOL')
    workbench_edit.add_argument('--add-stage', action='append', default=[], metavar='STAGE')
    workbench_edit.add_argument('--clone-stage', action='append', default=[], metavar='SRC:NEW')
    workbench_edit.add_argument('--mesh-size', type=float, default=None)
    workbench_edit.add_argument('--set-predecessor', action='append', default=[], metavar='STAGE=PRED')
    workbench_validate = sub.add_parser('workbench-validate-case', help='Validate a portable case through the next-generation workbench services')
    workbench_validate.add_argument('case_path', help='Path to a JSON or YAML case file')
    workbench_run = sub.add_parser('workbench-run-case', help='Use the next-generation workbench services to plan and run a case, then summarize results')
    workbench_run.add_argument('case_path', help='Path to a JSON or YAML case file')
    workbench_run.add_argument('--out-dir', default='exports_workbench', help='Directory for exported case files')
    _add_runtime_options(workbench_run, default_profile='cpu-robust', default_device='cpu')
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'check-env':
            print(format_environment_report(collect_environment_checks()))
            return
        if args.cmd == 'gui':
            _run_gui()
            return
        if args.cmd == 'demo':
            _run_demo(Path(args.out_dir), execution_profile=args.execution_profile, device=args.device)
            return
        if args.cmd == 'export-demo-case':
            _export_demo_case(Path(args.out))
            return
        if args.cmd == 'prepare-case':
            _prepare_case(Path(args.case_path))
            return
        if args.cmd == 'inspect-case':
            _inspect_case(Path(args.case_path))
            return
        if args.cmd == 'stage-graph-case':
            _stage_graph_case(Path(args.case_path))
            return
        if args.cmd == 'validate-case':
            _validate_case(Path(args.case_path))
            return
        if args.cmd == 'preprocess-case':
            _preprocess_case(Path(args.case_path))
            return
        if args.cmd == 'export-preprocess':
            _export_preprocess(Path(args.case_path), Path(args.out))
            return
        if args.cmd == 'adjacency-case':
            _adjacency_case(Path(args.case_path), min_shared_points=args.min_shared_points, mode=args.mode)
            return
        if args.cmd == 'topology-case':
            _topology_case(Path(args.case_path), duplicate_side=args.duplicate_side)
            return
        if args.cmd == 'interface-ready-case':
            _interface_ready_case(Path(args.case_path))
            return
        if args.cmd == 'interface-elements-case':
            _interface_elements_case(Path(args.case_path))
            return
        if args.cmd == 'export-interface-elements':
            _export_interface_elements(Path(args.case_path), Path(args.out))
            return
        if args.cmd == 'plan-case':
            _plan_case(Path(args.case_path), execution_profile=args.execution_profile, device=args.device, partition_count=args.partition_count, communicator_backend=args.communicator, checkpoint_policy=args.checkpoint_policy, checkpoint_dir=args.checkpoint_dir, checkpoint_every_n_increments=args.checkpoint_every, checkpoint_keep_last_n=args.checkpoint_keep_last, max_cutbacks=args.max_cutbacks, max_stage_retries=args.max_stage_retries, telemetry_level=args.telemetry_level, deterministic=args.deterministic, resume_checkpoint_id=args.resume_checkpoint_id)
            return
        if args.cmd == 'partition-case':
            _partition_case(Path(args.case_path), execution_profile=args.execution_profile, device=args.device, partition_count=args.partition_count, communicator_backend=args.communicator, checkpoint_policy=args.checkpoint_policy, checkpoint_dir=args.checkpoint_dir, checkpoint_every_n_increments=args.checkpoint_every, checkpoint_keep_last_n=args.checkpoint_keep_last, max_cutbacks=args.max_cutbacks, max_stage_retries=args.max_stage_retries, telemetry_level=args.telemetry_level, deterministic=args.deterministic, resume_checkpoint_id=args.resume_checkpoint_id)
            return
        if args.cmd == 'compare-partitions-case':
            _compare_partitions_case(Path(args.case_path), execution_profile=args.execution_profile, partition_count=args.partition_count, abs_tol=args.abs_tol, rel_tol=args.rel_tol)
            return
        if args.cmd == 'workbench-case':
            _workbench_case(Path(args.case_path))
            return
        if args.cmd == 'workbench-edit-case':
            _workbench_edit_case(Path(args.case_path), Path(args.out), args)
            return
        if args.cmd == 'workbench-validate-case':
            _workbench_validate_case(Path(args.case_path))
            return
        if args.cmd == 'workbench-run-case':
            _workbench_run_case(Path(args.case_path), Path(args.out_dir), execution_profile=args.execution_profile, device=args.device, partition_count=args.partition_count, communicator_backend=args.communicator, checkpoint_policy=args.checkpoint_policy, checkpoint_dir=args.checkpoint_dir, checkpoint_every_n_increments=args.checkpoint_every, checkpoint_keep_last_n=args.checkpoint_keep_last, max_cutbacks=args.max_cutbacks, max_stage_retries=args.max_stage_retries, telemetry_level=args.telemetry_level, deterministic=args.deterministic, resume_checkpoint_id=args.resume_checkpoint_id)
            return
        if args.cmd == 'run-case':
            _run_case(Path(args.case_path), Path(args.out_dir), execution_profile=args.execution_profile, device=args.device, partition_count=args.partition_count, communicator_backend=args.communicator, checkpoint_policy=args.checkpoint_policy, checkpoint_dir=args.checkpoint_dir, checkpoint_every_n_increments=args.checkpoint_every, checkpoint_keep_last_n=args.checkpoint_keep_last, max_cutbacks=args.max_cutbacks, max_stage_retries=args.max_stage_retries, telemetry_level=args.telemetry_level, deterministic=args.deterministic, resume_checkpoint_id=args.resume_checkpoint_id)
            return
        if args.cmd == 'checkpoint-list':
            _checkpoint_list(Path(args.checkpoint_dir))
            return
        if args.cmd == 'checkpoint-show':
            _checkpoint_show(Path(args.checkpoint_dir), args.checkpoint_id)
            return
        if args.cmd == 'checkpoint-validate':
            _checkpoint_validate(Path(args.checkpoint_dir), args.checkpoint_id)
            return
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    parser.error(f'Unknown command: {args.cmd}')


if __name__ == '__main__':
    main()
