from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from geoai_simkit.app.navigation import PrimarySpace, WorkbenchViewMode, build_primary_navigation, build_view_mode_options
from geoai_simkit.app.workspace_aliases import canonical_space
from geoai_simkit.app.workbench import WorkbenchDocument

PhaseStatus = Literal['locked', 'draft', 'ready', 'active', 'done', 'attention']


@dataclass(slots=True)
class WorkflowPhase:
    key: str
    label: str
    status: PhaseStatus
    progress: int
    summary: str
    next_action: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'key': self.key,
            'label': self.label,
            'status': self.status,
            'progress': int(self.progress),
            'summary': self.summary,
            'next_action': self.next_action,
            'metadata': dict(self.metadata),
        }


@dataclass(slots=True)
class WorkbenchSessionState:
    case_name: str
    lifecycle: str
    active_space: PrimarySpace
    active_view: WorkbenchViewMode
    phases: tuple[WorkflowPhase, ...]
    navigation: tuple[dict[str, Any], ...]
    available_views: tuple[dict[str, Any], ...]
    recommended_space: PrimarySpace
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'case_name': self.case_name,
            'lifecycle': self.lifecycle,
            'active_space': self.active_space,
            'active_view': self.active_view,
            'phases': [phase.to_dict() for phase in self.phases],
            'navigation': list(self.navigation),
            'available_views': list(self.available_views),
            'recommended_space': self.recommended_space,
            'metadata': dict(self.metadata),
        }


def _resolve_active_space(document: WorkbenchDocument) -> PrimarySpace:
    mapping: dict[str, PrimarySpace] = {
        'geometry': 'modeling',
        'partition': 'modeling',
        'mesh': 'mesh',
        'assign': 'modeling',
        'stage': 'modeling',
        'solve': 'solve',
        'results': 'results',
    }
    return mapping.get(document.mode, 'modeling')


def _resolve_lifecycle(document: WorkbenchDocument) -> str:
    if document.results is not None:
        return 'solved'
    if document.compile_report or document.checkpoint_ids:
        return 'runtime-ready'
    if document.validation is not None and document.validation.ok and document.preprocess is not None:
        return 'ready-to-run'
    if document.validation is not None:
        return 'editing'
    return 'draft'


def build_workbench_session_state(document: WorkbenchDocument, *, active_view: WorkbenchViewMode = 'workflow', active_space: PrimarySpace | str | None = None) -> WorkbenchSessionState:
    validation = document.validation
    preprocess = document.preprocess
    results = document.results
    has_compile = bool(document.compile_report)
    has_bundle = bool(document.metadata.get('runtime_bundle_path') or document.metadata.get('resumed_runtime_bundle_path'))
    phases = (
        WorkflowPhase('modeling', 'Modeling', 'done' if document.file_path else 'draft', 100 if document.file_path else 60, document.file_path or 'Case is currently unsaved.', 'Save a named case snapshot.' if not document.file_path else 'Continue editing model content.'),
        WorkflowPhase('mesh', 'Mesh', 'done' if document.browser.blocks else 'draft', 100 if document.browser.blocks else 35, f"{document.browser.object_count} objects, {len(document.browser.blocks)} blocks, {len(document.browser.stage_rows)} stages.", 'Bind materials and confirm stage activation.' if document.browser.blocks else 'Create geometry or import IFC/mesh sources.'),
        WorkflowPhase('solve', 'Solve', 'ready' if validation is not None and validation.ok and preprocess is not None else ('attention' if validation is not None else 'draft'), 100 if has_compile else (70 if validation is not None and validation.ok else 35), (f"Validation ok; compile report {'available' if has_compile else 'pending'}." if validation is not None and validation.ok else ('Validation not run yet.' if validation is None else f"{validation.error_count} errors, {validation.warning_count} warnings.")), 'Plan and launch the solver.' if validation is not None and validation.ok else 'Resolve validation issues before running.', {'preprocess_ready': preprocess is not None, 'compile_report_available': has_compile}),
        WorkflowPhase('results', 'Results', 'done' if results is not None else 'locked', 100 if results is not None else 0, (f"{results.stage_count} stages and {results.field_count} fields are available." if results is not None else 'No results are currently loaded.'), 'Inspect stage fields and compare runs.' if results is not None else 'Run or resume a case first.'),
        WorkflowPhase('benchmark', 'Benchmark', 'attention' if validation is not None and (validation.error_count or validation.warning_count) else ('ready' if document.messages or document.telemetry_summary or has_compile else 'draft'), 100 if has_compile or document.telemetry_summary else (70 if validation is not None else 35), (f"{validation.error_count} errors, {validation.warning_count} warnings." if validation is not None and (validation.error_count or validation.warning_count) else f"{len(document.messages)} messages; telemetry {'available' if document.telemetry_summary else 'pending'}."), 'Open diagnostics to resolve blocking issues.' if validation is not None and (validation.error_count or validation.warning_count) else 'Review runtime, compile and delivery diagnostics when needed.'),
        WorkflowPhase('advanced', 'Advanced', 'done' if has_bundle else ('ready' if results is not None else 'locked'), 100 if has_bundle else (55 if results is not None else 0), 'Runtime bundle / delivery assets available.' if has_bundle else 'Delivery assets not assembled yet.', 'Build or audit the delivery package.' if results is not None else 'Complete a solver run before delivery.'),
    )
    navigation = tuple(item.to_dict() for item in build_primary_navigation(document))
    navigation_keys = {str(item['key']) for item in navigation}
    recommended_space = next((item['key'] for item in navigation if item.get('recommended')), _resolve_active_space(document))
    resolved_active_space = canonical_space(str(active_space or document.metadata.get('active_space') or _resolve_active_space(document)))
    if resolved_active_space not in navigation_keys:
        resolved_active_space = str(recommended_space)
    available_views = tuple(item.to_dict() for item in build_view_mode_options(document))
    enabled_views = {str(item['key']) for item in available_views if bool(item.get('enabled', True))}
    resolved_active_view = str(active_view or document.metadata.get('active_view_mode') or 'workflow')
    if resolved_active_view not in enabled_views:
        resolved_active_view = 'workflow' if 'workflow' in enabled_views else next(iter(enabled_views), 'workflow')
    return WorkbenchSessionState(document.case.name, _resolve_lifecycle(document), resolved_active_space, resolved_active_view, phases, navigation, available_views, recommended_space, {'dirty': bool(document.dirty), 'has_results': results is not None, 'has_compile_report': has_compile, 'checkpoint_count': len(document.checkpoint_ids), 'message_count': len(document.messages)})
