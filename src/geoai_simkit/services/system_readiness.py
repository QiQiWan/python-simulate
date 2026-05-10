from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.services.blueprint_progress import blueprint_progress_summary, build_release_gate_snapshot
from geoai_simkit.env_check import collect_environment_checks, environment_capability_summary, format_environment_report
from geoai_simkit.runtime import RuntimeBundleManager


@dataclass(slots=True)
class SystemReadinessIssue:
    severity: str
    category: str
    message: str
    remedy: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'severity': str(self.severity),
            'category': str(self.category),
            'message': str(self.message),
            'remedy': str(self.remedy),
            'metadata': dict(self.metadata),
        }


@dataclass(slots=True)
class SystemReadinessReport:
    overall_score: float
    readiness_level: str
    ready_flags: dict[str, bool] = field(default_factory=dict)
    issues: list[SystemReadinessIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    blueprint_summary: dict[str, Any] = field(default_factory=dict)
    blueprint_release_gates: list[dict[str, Any]] = field(default_factory=list)
    weakest_blueprint_modules: list[dict[str, Any]] = field(default_factory=list)
    environment_checks: list[dict[str, Any]] = field(default_factory=list)
    environment_report: str = ''
    runtime_bundle_health: dict[str, Any] | None = None
    delivery_profile: dict[str, Any] | None = None
    execution_plan: dict[str, Any] | None = None
    preflight_report: dict[str, Any] | None = None
    bundle_progress: dict[str, Any] | None = None
    launch_recommendation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'overall_score': float(self.overall_score),
            'readiness_level': str(self.readiness_level),
            'ready_flags': {str(key): bool(value) for key, value in self.ready_flags.items()},
            'issues': [item.to_dict() for item in self.issues],
            'issue_count': int(len(self.issues)),
            'recommendations': [str(item) for item in self.recommendations],
            'blueprint_summary': dict(self.blueprint_summary),
            'blueprint_release_gates': [dict(item) for item in self.blueprint_release_gates],
            'weakest_blueprint_modules': [dict(item) for item in self.weakest_blueprint_modules],
            'environment_checks': [dict(item) for item in self.environment_checks],
            'environment_report': str(self.environment_report),
            'runtime_bundle_health': None if self.runtime_bundle_health is None else dict(self.runtime_bundle_health),
            'delivery_profile': None if self.delivery_profile is None else dict(self.delivery_profile),
            'execution_plan': None if self.execution_plan is None else dict(self.execution_plan),
            'preflight_report': None if self.preflight_report is None else dict(self.preflight_report),
            'bundle_progress': None if self.bundle_progress is None else dict(self.bundle_progress),
            'launch_recommendation': dict(self.launch_recommendation),
            'metadata': dict(self.metadata),
        }


def _severity_rank(value: str) -> int:
    token = str(value).strip().lower()
    if token == 'error':
        return 3
    if token == 'warning':
        return 2
    if token == 'info':
        return 1
    return 0


def _readiness_level(score: float, ready_flags: dict[str, bool], issues: list[SystemReadinessIssue]) -> str:
    if ready_flags.get('core_ready', False) and score >= 90.0 and not any(item.severity == 'error' for item in issues):
        return 'usable_core'
    if ready_flags.get('core_ready', False) and score >= 75.0:
        return 'operational'
    if ready_flags.get('core_ready', False):
        return 'partial'
    return 'blocked'


def build_system_readiness_report(
    *,
    runtime_bundle_dir: str | Path | None = None,
    delivery_dir: str | Path | None = None,
) -> SystemReadinessReport:
    manager = RuntimeBundleManager()
    audit = manager.delivery_audit_report(runtime_bundle_dir)
    checks = collect_environment_checks()
    capability_summary = environment_capability_summary()
    env_rows = [
        {
            'name': str(item.name),
            'installed': bool(item.installed),
            'detail': str(item.detail),
            'group': str(item.group),
            'status': str(item.status),
            'action': str(item.action),
        }
        for item in checks
    ]
    issues: list[SystemReadinessIssue] = []
    for row in env_rows:
        status = str(row.get('status', 'ok')).lower()
        if status == 'ok':
            continue
        if status in {'missing', 'limited'}:
            severity = 'warning'
        else:
            severity = 'error'
        issues.append(
            SystemReadinessIssue(
                severity=severity,
                category=f"dependency:{row.get('group', 'optional')}",
                message=f"{row.get('name')} is {status}: {row.get('detail', '')}".strip(),
                remedy=str(row.get('action', '')),
                metadata={'module': row.get('name'), 'group': row.get('group'), 'status': status},
            )
        )

    ready_flags = {str(key): bool(value) for key, value in dict(audit.get('ready_flags', {}) or {}).items()}
    bundle_health = None if runtime_bundle_dir is None else manager.bundle_health_report(runtime_bundle_dir)
    execution_plan = None if runtime_bundle_dir is None else manager.runtime_bundle_execution_plan(runtime_bundle_dir)
    preflight_report = None if runtime_bundle_dir is None else manager.runtime_bundle_preflight_report(runtime_bundle_dir)
    if preflight_report is not None and not bool(preflight_report.get('preflight_ok', False)):
        issues.append(
            SystemReadinessIssue(
                severity='error',
                category='preflight',
                message='Current environment does not satisfy the preferred runtime-bundle execution plan.',
                remedy='; '.join(str(item) for item in list(preflight_report.get('recommended_actions', []) or [])[:3]) or 'Review the runtime-bundle preflight report before launch.',
                metadata={'bundle_dir': None if runtime_bundle_dir is None else str(runtime_bundle_dir), 'readiness_level': preflight_report.get('readiness_level')},
            )
        )

    if bundle_health is not None and not bool(bundle_health.get('ok', False)):
        issues.append(
            SystemReadinessIssue(
                severity='error',
                category='runtime-bundle',
                message='Runtime bundle validation failed or required bundle assets are missing.',
                remedy='Re-export the runtime bundle and make sure checkpoints, result store, and manifest are copied together.',
                metadata={'bundle_dir': str(runtime_bundle_dir), 'issue_count': int(bundle_health.get('issue_count', 0) or 0)},
            )
        )
    elif bundle_health is not None and not bool(bundle_health.get('usable_for_resume', False)):
        issues.append(
            SystemReadinessIssue(
                severity='warning',
                category='runtime-bundle',
                message='Runtime bundle can be inspected but is not resume-ready.',
                remedy='Enable stage or failure checkpoints and export a fresh runtime bundle for handoff.',
                metadata={'bundle_dir': str(runtime_bundle_dir)},
            )
        )
    native_compatibility = None if bundle_health is None else dict(bundle_health.get('native_compatibility', {}) or {})
    if native_compatibility and not bool(native_compatibility.get('supported', False)):
        issues.append(
            SystemReadinessIssue(
                severity='warning',
                category='native-compatibility',
                message='Current case is not fully compatible with the preferred native continuum solve path.',
                remedy='; '.join(str(item) for item in list(native_compatibility.get('recommended_actions', []) or [])[:2]) or 'Review the native compatibility report.',
                metadata={
                    'bundle_dir': None if runtime_bundle_dir is None else str(runtime_bundle_dir),
                    'mesh_family': native_compatibility.get('mesh_family'),
                    'path': native_compatibility.get('path'),
                },
            )
        )

    bundle_progress = None
    if preflight_report is not None:
        bundle_progress = dict(preflight_report.get('bundle_progress', {}) or {}) or None
    elif bundle_health is not None:
        bundle_progress = dict(dict(bundle_health.get('inspection', {}) or {}).get('bundle_progress', {}) or {}) or None

    delivery_profile = None
    if delivery_dir is not None:
        delivery_profile = manager.delivery_runtime_profile(delivery_dir)
        if not bool(delivery_profile.get('delivery_validation_ok', False)):
            issues.append(
                SystemReadinessIssue(
                    severity='error',
                    category='delivery-package',
                    message='Delivery package validation failed.',
                    remedy='Run delivery-validate and fix missing assets or checksum mismatches before handoff.',
                    metadata={'delivery_dir': str(delivery_dir)},
                )
            )
        elif not bool(delivery_profile.get('smoke_ready', False)):
            issues.append(
                SystemReadinessIssue(
                    severity='warning',
                    category='delivery-package',
                    message='Delivery package is valid but not fully smoke-ready.',
                    remedy='Run the packaged smoke test and verify the helper scripts and runtime bundle resume plan.',
                    metadata={'delivery_dir': str(delivery_dir)},
                )
            )

    if not ready_flags.get('core_ready', False):
        issues.append(
            SystemReadinessIssue(
                severity='error',
                category='core',
                message='Core numerical dependencies are incomplete; the software system cannot be considered runnable.',
                remedy='Install the core dependency set and rerun the environment check.',
            )
        )
    if not ready_flags.get('gui_ready', False):
        issues.append(
            SystemReadinessIssue(
                severity='info',
                category='gui',
                message='Desktop GUI dependencies are incomplete, so only headless/runtime workflows are fully ready.',
                remedy='Install the GUI extra if you need the full PySide6 + PyVista workbench.',
            )
        )
    if not ready_flags.get('gpu_ready', False):
        issues.append(
            SystemReadinessIssue(
                severity='info',
                category='gpu',
                message='GPU acceleration is not available in the current environment.',
                remedy='Install Warp/CUDA dependencies and validate the device runtime on target hardware.',
            )
        )
    distributed_available = bool(capability_summary.get('distributed_available', False))
    if bundle_health is not None and int(dict(bundle_health.get('inspection', {}) or {}).get('partition_count', 1) or 1) > 1 and not distributed_available:
        issues.append(
            SystemReadinessIssue(
                severity='warning',
                category='distributed',
                message='The selected runtime bundle uses multiple partitions, but no distributed MPI runtime is available in the current environment.',
                remedy='Install mpi4py and launch under mpiexec on the target machine, or resume in local inspection mode.',
                metadata={'partition_count': int(dict(bundle_health.get('inspection', {}) or {}).get('partition_count', 1) or 1)},
            )
        )
    if not ready_flags.get('meshing_ready', False):
        issues.append(
            SystemReadinessIssue(
                severity='info',
                category='meshing',
                message='Meshing extras are incomplete, so geometry-to-mesh workflows may be limited.',
                remedy='Install meshio/gmsh and confirm native OpenGL libraries are present.',
            )
        )

    score = 100.0
    penalties = {
        'error': 18.0,
        'warning': 8.0,
        'info': 3.0,
    }
    for item in issues:
        score -= penalties.get(item.severity, 0.0)
    score = max(0.0, min(100.0, score))
    readiness_level = _readiness_level(score, ready_flags, issues)

    preferred_launch_mode = 'headless'
    launch_reason = 'Headless tools are the safest default in the current environment.'
    if ready_flags.get('gui_ready', False):
        preferred_launch_mode = 'gui'
        launch_reason = 'Desktop dependencies are present, so the next-generation workbench can be launched directly.'
    if delivery_profile is not None:
        preferred_launch_mode = str(delivery_profile.get('preferred_launch_mode') or preferred_launch_mode)
        launch_reason = str(delivery_profile.get('reason') or launch_reason)

    recommendations = list(dict.fromkeys(
        [str(item) for item in audit.get('recommended_actions', []) or [] if str(item).strip()] +
        [item.remedy for item in sorted(issues, key=lambda row: _severity_rank(row.severity), reverse=True) if item.remedy]
    ))

    blueprint_summary = blueprint_progress_summary()
    release_gates = build_release_gate_snapshot()
    weakest_modules = list(blueprint_summary.get('weakest_modules', []) or [])

    metadata: dict[str, Any] = {
        'runtime_bundle_dir': None if runtime_bundle_dir is None else str(Path(runtime_bundle_dir)),
        'delivery_dir': None if delivery_dir is None else str(Path(delivery_dir)),
        'warning_count': int(sum(1 for item in issues if item.severity == 'warning')),
        'error_count': int(sum(1 for item in issues if item.severity == 'error')),
        'info_count': int(sum(1 for item in issues if item.severity == 'info')),
        'release_gate_count': int(len(release_gates)),
        'weakest_module_count': int(len(weakest_modules)),
    }
    if bundle_health is not None:
        metadata['bundle_resume_ready'] = bool(bundle_health.get('usable_for_resume', False))
        metadata['native_compatibility_supported'] = bool(dict(bundle_health.get('native_compatibility', {}) or {}).get('supported', False))
    if execution_plan is not None:
        metadata['execution_plan_ok'] = bool(execution_plan.get('ok', False))
        metadata['execution_plan_mode'] = execution_plan.get('preferred_mode')
    if preflight_report is not None:
        metadata['preflight_ok'] = bool(preflight_report.get('preflight_ok', False))
        metadata['preflight_level'] = preflight_report.get('readiness_level')
    if delivery_profile is not None:
        metadata['delivery_validation_ok'] = bool(delivery_profile.get('delivery_validation_ok', False))
        metadata['delivery_smoke_ready'] = bool(delivery_profile.get('smoke_ready', False))
        metadata['preferred_execution_profile'] = delivery_profile.get('preferred_execution_profile')
        metadata['preferred_device'] = delivery_profile.get('preferred_device')
        metadata['preferred_communicator_backend'] = delivery_profile.get('preferred_communicator_backend')

    return SystemReadinessReport(
        overall_score=score,
        readiness_level=readiness_level,
        ready_flags=ready_flags,
        issues=issues,
        recommendations=recommendations,
        blueprint_summary=blueprint_summary,
        blueprint_release_gates=release_gates,
        weakest_blueprint_modules=weakest_modules,
        environment_checks=env_rows,
        environment_report=format_environment_report(checks),
        runtime_bundle_health=bundle_health,
        delivery_profile=delivery_profile,
        execution_plan=execution_plan,
        preflight_report=preflight_report,
        bundle_progress=bundle_progress,
        launch_recommendation={
            'preferred_launch_mode': preferred_launch_mode,
            'reason': launch_reason,
            'preferred_execution_profile': (
                delivery_profile.get('preferred_execution_profile')
                if delivery_profile is not None and delivery_profile.get('preferred_execution_profile') not in {None, ''}
                else (None if execution_plan is None else dict(execution_plan.get('native_execution_target', {}) or {}).get('preferred_execution_profile'))
            ),
            'preferred_device': (
                delivery_profile.get('preferred_device')
                if delivery_profile is not None and delivery_profile.get('preferred_device') not in {None, ''}
                else (None if execution_plan is None else dict(execution_plan.get('native_execution_target', {}) or {}).get('preferred_device'))
            ),
            'preferred_communicator_backend': (
                delivery_profile.get('preferred_communicator_backend')
                if delivery_profile is not None and delivery_profile.get('preferred_communicator_backend') not in {None, ''}
                else (None if execution_plan is None else dict(execution_plan.get('native_execution_target', {}) or {}).get('preferred_communicator_backend'))
            ),
            'recommended_command': (
                delivery_profile.get('recommended_command')
                if delivery_profile is not None and delivery_profile.get('recommended_command') not in {None, ''}
                else (None if execution_plan is None else execution_plan.get('recommended_command'))
            ),
        },
        metadata=metadata,
    )


def render_system_readiness_markdown(
    *,
    runtime_bundle_dir: str | Path | None = None,
    delivery_dir: str | Path | None = None,
    title: str = 'System Readiness Report',
) -> str:
    report = build_system_readiness_report(runtime_bundle_dir=runtime_bundle_dir, delivery_dir=delivery_dir)
    payload = report.to_dict()
    lines = [
        f'# {title}',
        '',
        f"- Overall score: **{payload['overall_score']:.1f}/100**",
        f"- Readiness level: **{payload['readiness_level']}**",
        f"- Preferred launch mode: **{payload['launch_recommendation'].get('preferred_launch_mode', 'headless')}**",
        f"- Launch guidance: {payload['launch_recommendation'].get('reason', '')}",
        f"- Preferred execution profile: **{payload['launch_recommendation'].get('preferred_execution_profile', '<n/a>')}**",
        f"- Preferred device: **{payload['launch_recommendation'].get('preferred_device', '<n/a>')}**",
        f"- Preferred communicator: **{payload['launch_recommendation'].get('preferred_communicator_backend', '<n/a>')}**",
        f"- Recommended command: `{payload['launch_recommendation'].get('recommended_command', '')}`",
        '',
        '## Ready Flags',
        '',
    ]
    for key in sorted(payload['ready_flags']):
        lines.append(f"- {key}: **{payload['ready_flags'][key]}**")
    lines.extend(['', '## Blueprint Summary', ''])
    blueprint = dict(payload.get('blueprint_summary', {}) or {})
    for key in ('overall_percent', 'module_count'):
        if key in blueprint:
            lines.append(f"- {key}: **{blueprint[key]}**")
    by_plane = dict(blueprint.get('by_plane', {}) or {})
    if by_plane:
        lines.append('- by_plane:')
        for key in sorted(by_plane):
            lines.append(f"  - {key}: {by_plane[key]}")
    preflight = dict(payload.get('preflight_report', {}) or {})
    if preflight:
        lines.extend(['', '## Runtime Bundle Preflight', ''])
        lines.append(f"- Readiness level: **{preflight.get('readiness_level', 'blocked')}**")
        lines.append(f"- Preflight ok: **{bool(preflight.get('preflight_ok'))}**")
        lines.append(f"- Recommended command: `{preflight.get('recommended_command', '')}`")
        if list(preflight.get('blockers', []) or []):
            lines.append(f"- blockers: {'; '.join(str(item) for item in list(preflight.get('blockers', []) or []))}")
        bundle_progress = dict(preflight.get('bundle_progress', {}) or {})
        if bundle_progress:
            latest_stage = dict(bundle_progress.get('latest_stage', {}) or {})
            if latest_stage:
                lines.append(f"- Latest stage: **{latest_stage.get('stage_name', '<unknown>')}** ({latest_stage.get('status', 'unknown')})")
            failed = list(bundle_progress.get('failed_stage_names', []) or [])
            if failed:
                lines.append(f"- Failed stages: {'; '.join(str(item) for item in failed)}")
            diagnostics = bundle_progress.get('latest_stage_diagnostics')
            if diagnostics is not None and diagnostics != '':
                lines.append(f"- Latest diagnostics: `{diagnostics}`")
            paths = list(bundle_progress.get('execution_path_labels', []) or [])
            if paths:
                lines.append(f"- Execution paths: {', '.join(str(item) for item in paths)}")
            local_count = int(bundle_progress.get('total_partition_local_system_count', 0) or 0)
            if local_count:
                lines.append(f"- Partition-local systems: **{local_count}**")
    execution_plan = dict(payload.get('execution_plan', {}) or {})
    if execution_plan:
        lines.extend(['', '## Runtime Bundle Execution Plan', ''])
        lines.append(f"- Preferred mode: **{execution_plan.get('preferred_mode', 'inspect')}**")
        lines.append(f"- Recommended command: `{execution_plan.get('recommended_command', '')}`")
        blockers = list(execution_plan.get('blockers', []) or [])
        if blockers:
            lines.append(f"- blockers: {'; '.join(str(item) for item in blockers)}")
    release_gates = list(payload.get('blueprint_release_gates', []) or [])
    if release_gates:
        lines.extend(['', '## Release Gates', ''])
        for gate in release_gates:
            lines.append(f"- **{gate.get('title', '<gate>')}**: {gate.get('percent_complete', 0)}% ({gate.get('status', 'unknown')})")
            blockers = list(gate.get('blockers', []) or [])
            if blockers:
                lines.append(f"  - blockers: {'; '.join(str(item) for item in blockers)}")
    weakest = list(payload.get('weakest_blueprint_modules', []) or [])
    if weakest:
        lines.extend(['', '## Lowest-completion modules', ''])
        for item in weakest[:5]:
            lines.append(f"- **{item.get('title', '<module>')}**: {item.get('percent_complete', 0)}%")
    lines.extend(['', '## Issues', ''])
    issues = list(payload.get('issues', []) or [])
    if not issues:
        lines.append('- No blocking issues were detected.')
    else:
        for item in issues:
            lines.append(f"- **{item.get('severity', 'info')}** [{item.get('category', 'general')}] {item.get('message', '')}")
            if item.get('remedy'):
                lines.append(f"  - Remedy: {item['remedy']}")
    recommendations = list(payload.get('recommendations', []) or [])
    if recommendations:
        lines.extend(['', '## Recommended Actions', ''])
        for item in recommendations:
            lines.append(f'- {item}')
    if payload.get('runtime_bundle_health') is not None:
        bundle = dict(payload['runtime_bundle_health'] or {})
        lines.extend(['', '## Runtime Bundle Health', ''])
        for key in ('ok', 'usable_for_resume', 'issue_count', 'checkpoint_count', 'stage_count', 'field_count'):
            if key in bundle:
                lines.append(f"- {key}: **{bundle[key]}**")
    bundle_progress = dict(payload.get('bundle_progress', {}) or {})
    if bundle_progress:
        lines.extend(['', '## Bundle Progress', ''])
        latest_stage = dict(bundle_progress.get('latest_stage', {}) or {})
        if latest_stage:
            lines.append(f"- Latest stage: **{latest_stage.get('stage_name', '<unknown>')}**")
            lines.append(f"- Latest stage status: **{latest_stage.get('status', 'unknown')}**")
        failed = list(bundle_progress.get('failed_stage_names', []) or [])
        if failed:
            lines.append(f"- Failed stages: {'; '.join(str(item) for item in failed)}")
        diagnostics = bundle_progress.get('latest_stage_diagnostics')
        if diagnostics is not None and diagnostics != '':
            lines.append(f"- Latest diagnostics: `{diagnostics}`")
        paths = list(bundle_progress.get('execution_path_labels', []) or [])
        if paths:
            lines.append(f"- Execution paths: {', '.join(str(item) for item in paths)}")
        local_count = int(bundle_progress.get('total_partition_local_system_count', 0) or 0)
        if local_count:
            lines.append(f"- Partition-local systems: **{local_count}**")
    if payload.get('delivery_profile') is not None:
        profile = dict(payload['delivery_profile'] or {})
        lines.extend(['', '## Delivery Profile', ''])
        for key in ('preferred_launch_mode', 'delivery_validation_ok', 'smoke_ready', 'resume_ready', 'gui_available', 'has_runtime_bundle'):
            if key in profile:
                lines.append(f"- {key}: **{profile[key]}**")
    return '\n'.join(lines) + '\n'


__all__ = [
    'SystemReadinessIssue',
    'SystemReadinessReport',
    'build_system_readiness_report',
    'render_system_readiness_markdown',
]
