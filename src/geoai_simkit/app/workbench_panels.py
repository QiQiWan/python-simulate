from __future__ import annotations

from typing import Any

from geoai_simkit.app.blueprint_progress import build_blueprint_progress_snapshot, blueprint_progress_summary, build_release_gate_snapshot
from geoai_simkit.app.workbench import WorkbenchDocument


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def build_workflow_metric_rows(document: WorkbenchDocument) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ('Mode', str(document.mode)),
        ('Model', str(document.browser.model_name)),
        ('Geometry state', str(document.browser.geometry_state)),
        ('Blocks', str(len(document.browser.blocks))),
        ('Stages', str(len(document.browser.stage_rows))),
        ('Interfaces', str(document.browser.interface_count)),
        ('Interface elements', str(document.browser.interface_element_count)),
        ('Structures', str(document.browser.structure_count)),
        ('Dirty', str(bool(document.dirty))),
    ]
    if document.preprocess is not None:
        rows.extend([
            ('Boundary adjacencies', str(document.preprocess.n_boundary_adjacencies)),
            ('Interface candidates', str(document.preprocess.n_interface_candidates)),
            ('Preprocessor interface elements', str(document.preprocess.n_interface_elements)),
        ])
    if document.validation is not None:
        rows.extend([
            ('Validation errors', str(document.validation.error_count)),
            ('Validation warnings', str(document.validation.warning_count)),
            ('Validation info', str(document.validation.info_count)),
        ])
    if document.job_plan is not None:
        rows.extend([
            ('Planned profile', str(document.job_plan.profile)),
            ('Planned device', str(document.job_plan.device)),
            ('Estimated partitions', str(document.job_plan.estimated_partitions or 0)),
            ('Estimated peak memory bytes', str(document.job_plan.estimated_peak_memory_bytes or 0)),
        ])
    if document.results is not None:
        rows.extend([
            ('Result stages', str(document.results.stage_count)),
            ('Result fields', str(document.results.field_count)),
        ])
    if document.checkpoint_ids:
        rows.append(('Stage checkpoints', str(len(document.checkpoint_ids))))
    if document.increment_checkpoint_ids:
        rows.append(('Increment checkpoints', str(len(document.increment_checkpoint_ids))))
    if document.failure_checkpoint_ids:
        rows.append(('Failure checkpoints', str(len(document.failure_checkpoint_ids))))
    runtime_meta = dict(document.metadata.get('runtime_metadata', {}) or {})
    blueprint = dict(document.metadata.get('blueprint_progress', {}) or {})
    if not blueprint:
        blueprint = {
            'summary': blueprint_progress_summary(),
            'release_gates': build_release_gate_snapshot(),
        }
    summary = dict(blueprint.get('summary', {}) or {})
    weakest_modules = list(summary.get('weakest_modules', []) or [])
    release_gates = list(blueprint.get('release_gates', summary.get('release_gates', []) or []) or [])
    if summary:
        rows.extend([
            ('Blueprint overall progress', f"{_safe_float(summary.get('overall_percent', 0.0)):.1f}%"),
            ('Tracked modules', str(_safe_int(summary.get('module_count', 0)))),
            ('Release gates', str(len(release_gates))),
            ('Lowest module progress', f"{_safe_float((weakest_modules[0] if weakest_modules else {}).get('percent_complete', 0.0)):.1f}%"),
        ])
    system_readiness = dict(document.metadata.get('system_readiness', {}) or {})
    if runtime_meta:
        rows.extend([
            ('Max active structures', str(_safe_int(runtime_meta.get('max_active_structure_count', 0)))),
            ('Max active interfaces', str(_safe_int(runtime_meta.get('max_active_interface_count', 0)))),
            ('Max active contact pairs', str(_safe_int(runtime_meta.get('max_active_contact_pair_count', 0)))),
            ('Max structural rotational DOFs', str(_safe_int(runtime_meta.get('max_active_structural_rotational_dof_count', 0)))),
            ('Max structural rotation constraints', str(_safe_int(runtime_meta.get('max_structural_rotation_constraint_count', 0)))),
            ('Max structural hybrid tail DOFs', str(_safe_int(runtime_meta.get('max_structural_hybrid_tail_dof_count', 0)))),
            ('Max structural load entries', str(_safe_int(runtime_meta.get('max_structural_load_entry_count', 0)))),
            ('Tet4 completed stages', str(_safe_int(dict(runtime_meta.get('tet4_runtime_diagnostics', {}) or {}).get('completed_stage_count', 0)))),
        ])
    scene_preview = dict(document.metadata.get('scene_preview', {}) or {})
    if scene_preview:
        rows.extend([
            ('Scene dataset kind', str(scene_preview.get('dataset_kind', '<unknown>'))),
            ('Scene points', str(_safe_int(scene_preview.get('point_count', 0)))),
            ('Scene cells', str(_safe_int(scene_preview.get('cell_count', 0)))),
        ])
    native_compatibility = dict(document.metadata.get('native_compatibility', {}) or {})
    if native_compatibility:
        rows.extend([
            ('Native mesh family', str(native_compatibility.get('mesh_family', '<unknown>'))),
            ('Native path', str(native_compatibility.get('path', '<unknown>'))),
            ('Native supported', str(bool(native_compatibility.get('supported', False)))),
            ('Native stage classifications', str(len(list(native_compatibility.get('stage_classifications', []) or [])))),
        ])
    bundle_path = document.metadata.get('runtime_bundle_path')
    if bundle_path:
        rows.append(('Runtime bundle', str(bundle_path)))
    system_readiness = dict(document.metadata.get('system_readiness', {}) or {})
    if system_readiness:
        rows.extend([
            ('System readiness', str(system_readiness.get('readiness_level', '<unknown>'))),
            ('System readiness score', f"{_safe_float(system_readiness.get('overall_score', 0.0)):.1f}"),
            ('Preferred launch mode', str(dict(system_readiness.get('launch_recommendation', {}) or {}).get('preferred_launch_mode', '<unknown>'))),
            ('Recommended command', str(dict(system_readiness.get('launch_recommendation', {}) or {}).get('recommended_command', '<none>'))),
        ])
    delivery_audit = dict(document.metadata.get('delivery_audit', {}) or {})
    if delivery_audit:
        ready_flags = dict(delivery_audit.get('ready_flags', {}) or {})
        rows.extend([
            ('Delivery core ready', str(bool(ready_flags.get('core_ready', False)))),
            ('Delivery GUI ready', str(bool(ready_flags.get('gui_ready', False)))),
            ('Delivery bundle ready', str(bool(ready_flags.get('bundle_ready', False)))),
            ('Delivery resume ready', str(bool(ready_flags.get('resume_ready', False)))),
        ])
    delivery_path = document.metadata.get('delivery_package_path')
    if delivery_path:
        rows.append(('Delivery package', str(delivery_path)))
    return rows


def build_alert_rows(document: WorkbenchDocument) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if document.validation is not None:
        for issue in document.validation.issues:
            rows.append({
                'severity': str(issue.get('level', 'info')).lower(),
                'source': str(issue.get('code', 'validation')),
                'message': str(issue.get('message', '')),
                'hint': str(issue.get('hint', '')),
            })
    runtime_meta = dict(document.metadata.get('runtime_metadata', {}) or {})
    for key in ('unsupported_native_paths', 'interface_warnings', 'structural_warnings'):
        for idx, value in enumerate(runtime_meta.get(key, ()) or ()):
            rows.append({
                'severity': 'warning',
                'source': f'runtime:{key}:{idx}',
                'message': str(value),
                'hint': 'Review the native runtime diagnostics and stage overlay summary.',
            })
    native_compatibility = dict(document.metadata.get('native_compatibility', {}) or {})
    if native_compatibility and not bool(native_compatibility.get('supported', False)):
        reasons = list(native_compatibility.get('reasons', []) or [])
        if reasons:
            rows.append({
                'severity': 'warning',
                'source': 'runtime:native-compatibility',
                'message': str(reasons[0]),
                'hint': '; '.join(str(item) for item in list(native_compatibility.get('recommended_actions', []) or [])[:2]) or 'Review the native compatibility report.',
            })
    telemetry = dict(document.telemetry_summary or {})
    system_readiness = dict(document.metadata.get('system_readiness', {}) or {})
    if system_readiness and _safe_int(system_readiness.get('issue_count', len(system_readiness.get('issues', []) or []))) > 0:
        issue_rows = list(system_readiness.get('issues', []) or [])
        if issue_rows:
            top = issue_rows[0]
            rows.append({
                'severity': str(top.get('severity', 'warning')).lower(),
                'source': f"system:{top.get('category', 'readiness')}",
                'message': str(top.get('message', 'System readiness reported issues.')),
                'hint': str(top.get('remedy', 'Review the system-readiness report before release.')),
            })
    if _safe_int(telemetry.get('failed_increments')) > 0:
        rows.append({
            'severity': 'error',
            'source': 'telemetry:failed_increments',
            'message': f"Detected {telemetry.get('failed_increments')} failed increments in the current runtime history.",
            'hint': 'Inspect the stage history, cutback policy, and constitutive settings.',
        })
    if _safe_int(telemetry.get('cutback_count')) > 0:
        rows.append({
            'severity': 'warning',
            'source': 'telemetry:cutback_count',
            'message': f"Current runtime used {telemetry.get('cutback_count')} cutback(s).",
            'hint': 'Check stage load stepping and interface/contact stabilization.',
        })
    return rows


def build_runtime_log_lines(document: WorkbenchDocument) -> list[str]:
    lines: list[str] = []
    if document.messages:
        lines.extend(str(item) for item in document.messages)
    telemetry = dict(document.telemetry_summary or {})
    if telemetry:
        lines.append('--- telemetry summary ---')
        for key in sorted(telemetry):
            lines.append(f"{key}: {telemetry[key]}")
    compile_report = dict(document.compile_report or {})
    if compile_report:
        lines.append('--- compile report ---')
        for key in sorted(compile_report):
            lines.append(f"{key}: {compile_report[key]}")
    blueprint = dict(document.metadata.get('blueprint_progress', {}) or {})
    if not blueprint:
        blueprint = {
            'summary': blueprint_progress_summary(),
            'release_gates': build_release_gate_snapshot(),
        }
    summary = dict(blueprint.get('summary', {}) or {})
    weakest_modules = list(summary.get('weakest_modules', []) or [])
    release_gates = list(blueprint.get('release_gates', summary.get('release_gates', []) or []) or [])
    if summary:
        lines.append('--- blueprint progress ---')
        lines.append(f"overall_percent: {_safe_float(summary.get('overall_percent', 0.0)):.1f}%")
        lines.append(f"tracked_modules: {_safe_int(summary.get('module_count', 0))}")
        lines.append(f"release_gates: {len(release_gates)}")
        if weakest_modules:
            top = weakest_modules[0]
            lines.append(f"weakest_module: {top.get('title')} ({top.get('percent_complete')}%)")
    runtime_meta = dict(document.metadata.get('runtime_metadata', {}) or {})
    system_readiness = dict(document.metadata.get('system_readiness', {}) or {})
    if system_readiness:
        lines.append('--- system readiness ---')
        lines.append(f"readiness_level: {system_readiness.get('readiness_level')}")
        lines.append(f"overall_score: {system_readiness.get('overall_score')}")
        launch = dict(system_readiness.get('launch_recommendation', {}) or {})
        if launch:
            lines.append(f"preferred_launch_mode: {launch.get('preferred_launch_mode')}")
            lines.append(f"launch_reason: {launch.get('reason')}")
            lines.append(f"recommended_command: {launch.get('recommended_command')}")
    if runtime_meta:
        lines.append('--- runtime metadata ---')
        for key in sorted(runtime_meta):
            lines.append(f"{key}: {runtime_meta[key]}")
    native_compatibility = dict(document.metadata.get('native_compatibility', {}) or {})
    if native_compatibility:
        lines.append('--- native compatibility ---')
        lines.append(f"mesh_family: {native_compatibility.get('mesh_family')}")
        lines.append(f"path: {native_compatibility.get('path')}")
        lines.append(f"supported: {native_compatibility.get('supported')}")
        for row in list(native_compatibility.get('stage_classifications', []) or [])[:10]:
            lines.append(f"stage:{row.get('stage_name')} class={row.get('classification')} path={row.get('recommended_native_path')} supported={row.get('supported')}")
    if not lines:
        lines.append('No runtime log entries yet.')
    return lines


def build_scene_summary_rows(
    document: WorkbenchDocument,
    *,
    actor_map: dict[str, dict[str, Any]] | None = None,
    view_mode: str = 'normal',
    stage_name: str = '<model>',
) -> list[tuple[str, str]]:
    actor_map = dict(actor_map or {})
    active_regions = 0
    inactive_regions = 0
    if stage_name not in {None, '', '<model>'}:
        for block in document.browser.blocks:
            stage_rows = [row for row in document.browser.stage_rows if row.name == stage_name]
            if stage_rows:
                row = stage_rows[0]
                state = None
                if block.name in row.activate_regions:
                    state = True
                elif block.name in row.deactivate_regions:
                    state = False
                if state is False:
                    inactive_regions += 1
                else:
                    active_regions += 1
    selected_bundle = document.metadata.get('runtime_bundle_path') or document.metadata.get('resumed_runtime_bundle_path') or ''
    scene_preview = dict(document.metadata.get('scene_preview', {}) or {})
    scene_bounds = tuple(scene_preview.get('bounds', ()) or ())
    bounds_text = '<none>' if not scene_bounds else ', '.join(f"{float(v):.3g}" for v in scene_bounds[:6])
    return [
        ('View mode', str(view_mode)),
        ('Displayed stage', str(stage_name)),
        ('Viewport actors', str(len(actor_map))),
        ('Browser blocks', str(len(document.browser.blocks))),
        ('Scene dataset', str(scene_preview.get('dataset_kind', '<unknown>'))),
        ('Scene points', str(_safe_int(scene_preview.get('point_count', 0)))),
        ('Scene cells', str(_safe_int(scene_preview.get('cell_count', 0)))),
        ('Scene bounds', bounds_text),
        ('Results loaded', str(bool(document.results is not None))),
        ('Active regions', str(active_regions)),
        ('Inactive regions', str(inactive_regions)),
        ('Bundle linked', str(bool(selected_bundle))),
        ('Selected bundle path', str(selected_bundle or '<none>')),
    ]


def build_blueprint_progress_rows(document: WorkbenchDocument) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    runtime_bundle_path = document.metadata.get('runtime_bundle_path')
    for item in build_blueprint_progress_snapshot():
        summary = item.summary
        if item.module_id == 'result_plane' and runtime_bundle_path:
            summary += f' Current document bundle: {runtime_bundle_path}.'
        rows.append({
            'plane': item.plane,
            'module': item.title,
            'section': item.blueprint_section,
            'progress': f'{item.percent_complete}%',
            'status': item.status,
            'summary': summary,
            'next_steps': '; '.join(item.next_steps),
            'blockers': '; '.join(item.blockers),
        })
    return rows


def build_key_process_rows(document: WorkbenchDocument) -> list[dict[str, str]]:
    stage_count = len(document.browser.stage_rows)
    validation = document.validation
    telemetry = dict(document.telemetry_summary or {})
    return [
        {
            'item': 'Geometry import / browser',
            'state': 'ready' if document.browser.object_count or document.browser.blocks else 'empty',
            'detail': f"objects={document.browser.object_count} blocks={len(document.browser.blocks)}",
        },
        {
            'item': 'Stage compilation',
            'state': 'ready' if stage_count else 'missing',
            'detail': f"stages={stage_count}",
        },
        {
            'item': 'Validation',
            'state': 'ok' if validation and validation.ok else ('issues' if validation else 'unknown'),
            'detail': (f"E={validation.error_count} W={validation.warning_count} I={validation.info_count}" if validation else 'validation not run'),
        },
        {
            'item': 'Runtime / solve',
            'state': 'available' if (document.results is not None or document.job_plan is not None) else 'idle',
            'detail': f"cutbacks={telemetry.get('cutback_count', 0)} failed_increments={telemetry.get('failed_increments', 0)}",
        },
        {
            'item': 'Structural / interface overlays',
            'state': 'ready' if document.metadata.get('runtime_metadata') else 'unknown',
            'detail': (
                f"struct={_safe_int(dict(document.metadata.get('runtime_metadata', {}) or {}).get('max_active_structure_count', 0))} "
                f"interface={_safe_int(dict(document.metadata.get('runtime_metadata', {}) or {}).get('max_active_interface_count', 0))} "
                f"contact={_safe_int(dict(document.metadata.get('runtime_metadata', {}) or {}).get('max_active_contact_pair_count', 0))}"
            ),
        },
        {
            'item': 'Bundle / restart',
            'state': 'ready' if document.metadata.get('runtime_bundle_path') else 'not-exported',
            'detail': f"checkpoints={len(document.checkpoint_ids)} incremental={len(document.increment_checkpoint_ids)} failure={len(document.failure_checkpoint_ids)}",
        },
        {
            'item': 'Delivery package',
            'state': 'ready' if document.metadata.get('delivery_package_path') else ('audited' if document.metadata.get('delivery_audit') else 'not-audited'),
            'detail': f"bundle_ready={bool(dict(document.metadata.get('delivery_audit', {}) or {}).get('ready_flags', {}).get('bundle_ready', False))} gui_ready={bool(dict(document.metadata.get('delivery_audit', {}) or {}).get('ready_flags', {}).get('gui_ready', False))}",
        },
        {
            'item': 'System readiness',
            'state': str(dict(document.metadata.get('system_readiness', {}) or {}).get('readiness_level', 'unknown')),
            'detail': f"score={_safe_float(dict(document.metadata.get('system_readiness', {}) or {}).get('overall_score', 0.0)):.1f} launch={dict(dict(document.metadata.get('system_readiness', {}) or {}).get('launch_recommendation', {}) or {}).get('preferred_launch_mode', '<unknown>')}",
        },
    ]


__all__ = [
    'build_alert_rows',
    'build_blueprint_progress_rows',
    'build_key_process_rows',
    'build_runtime_log_lines',
    'build_scene_summary_rows',
    'build_workflow_metric_rows',
]
