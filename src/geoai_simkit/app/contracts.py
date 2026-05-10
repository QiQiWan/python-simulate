from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PRIMARY_SPACES: tuple[str, ...] = ('modeling', 'mesh', 'solve', 'results', 'benchmark', 'advanced')
LEGACY_PRIMARY_SPACE_ALIASES: dict[str, str] = {'project': 'modeling', 'model': 'mesh', 'diagnostics': 'benchmark', 'delivery': 'advanced'}
SYSTEM_CONSOLE_TABS: tuple[str, ...] = ('alerts', 'runtime_log', 'jobs', 'validation')
MODEL_STUDIOS: tuple[str, ...] = (
    'geometry_studio',
    'material_region_studio',
    'structures_interfaces_studio',
    'stage_designer',
    'mesh_readiness',
)
SOLVE_PANELS: tuple[str, ...] = ('ready_gate', 'pre_solve_check', 'run_control', 'runtime_board', 'recovery_panel')
RESULTS_SPACES: tuple[str, ...] = ('stage_browser', 'field_compare', 'result_audit', 'export_delivery')
DELIVERY_SECTIONS: tuple[str, ...] = ('package_manifest', 'delivery_audit', 'export_center', 'lineage_center')


@dataclass(frozen=True, slots=True)
class ContractSection:
    key: str
    label: str
    role: str
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'key': self.key,
            'label': self.label,
            'role': self.role,
            'required': bool(self.required),
            'metadata': dict(self.metadata),
        }


def _section(key: str, label: str, role: str, **metadata: Any) -> dict[str, Any]:
    return ContractSection(key=key, label=label, role=role, metadata=metadata).to_dict()


def _as_dict_rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in list(value or []) if isinstance(row, dict)]


def _as_str_list(value: Any) -> list[str]:
    rows: list[str] = []
    for item in list(value or []):
        text = str(item or '')
        if text and text not in rows:
            rows.append(text)
    return rows


def _issue(
    issue_id: str,
    severity: str,
    message: str,
    *,
    target: str,
    action: str | None = None,
    jump: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_severity = str(severity or 'info').lower()
    if normalized_severity not in {'info', 'warning', 'blocking'}:
        normalized_severity = 'info'
    return {
        'id': str(issue_id),
        'severity': normalized_severity,
        'message': str(message),
        'target': str(target),
        'action': action,
        'jump': jump or target,
        'details': dict(details or {}),
    }


def _state_from_stage(stage: dict[str, Any], region: str) -> str:
    activation_map = dict(stage.get('activation_map', {}) or {})
    if region in activation_map:
        return 'active' if bool(activation_map[region]) else 'inactive'
    active_regions = {str(name) for name in list(stage.get('activate_regions', []) or [])}
    inactive_regions = {str(name) for name in list(stage.get('deactivate_regions', []) or [])}
    in_active = region in active_regions
    in_inactive = region in inactive_regions
    if in_active and in_inactive:
        return 'conflict'
    if in_active:
        return 'active'
    if in_inactive:
        return 'inactive'
    return 'inherit'


def _build_stage_matrix(stages: list[dict[str, Any]], regions: list[str]) -> dict[str, Any]:
    stage_lookup = {str(stage.get('name') or ''): stage for stage in stages if str(stage.get('name') or '')}
    explicit_lookup: dict[tuple[str, str], str] = {}
    effective_lookup: dict[tuple[str, str], str] = {}
    inherited_from_lookup: dict[tuple[str, str], str | None] = {}

    def resolve(stage_name: str, region: str, trail: tuple[str, ...] = ()) -> tuple[str, str | None]:
        key = (stage_name, region)
        if key in effective_lookup:
            return effective_lookup[key], inherited_from_lookup.get(key)
        stage = stage_lookup.get(stage_name, {})
        explicit = _state_from_stage(stage, region)
        explicit_lookup[key] = explicit
        if explicit != 'inherit':
            effective_lookup[key] = explicit
            inherited_from_lookup[key] = None
            return explicit, None
        predecessor = str(stage.get('predecessor') or '')
        if predecessor and predecessor in stage_lookup and predecessor not in trail:
            inherited, inherited_from = resolve(predecessor, region, (*trail, stage_name))
            effective_lookup[key] = inherited
            inherited_from_lookup[key] = inherited_from or predecessor
            return inherited, inherited_from_lookup[key]
        effective_lookup[key] = 'inherit'
        inherited_from_lookup[key] = None
        return 'inherit', None

    rows: list[dict[str, Any]] = []
    conflict_cells: list[dict[str, Any]] = []
    inherited_cell_count = 0
    explicit_cell_count = 0
    state_counts = {'active': 0, 'inactive': 0, 'inherit': 0, 'conflict': 0}
    for region in regions:
        cells: list[dict[str, Any]] = []
        previous_effective = 'inherit'
        for stage in stages:
            stage_name = str(stage.get('name') or '')
            explicit = _state_from_stage(stage, region)
            effective, inherited_from = resolve(stage_name, region)
            changed = bool(stage_name and effective != previous_effective and effective != 'inherit')
            previous_effective = effective
            explicit_cell_count += 0 if explicit == 'inherit' else 1
            inherited_cell_count += 1 if explicit == 'inherit' and inherited_from else 0
            state_counts[effective if effective in state_counts else 'inherit'] += 1
            cell = {
                'stage_name': stage_name,
                'state': explicit,
                'explicit_state': explicit,
                'effective_state': effective,
                'explicit': explicit != 'inherit',
                'inherited_from': inherited_from,
                'changed': changed,
                'severity': 'blocking' if explicit == 'conflict' else ('info' if explicit != 'inherit' else 'muted'),
            }
            if explicit == 'conflict':
                conflict_cells.append({'region_name': region, 'stage_name': stage_name})
            cells.append(cell)
        rows.append({'region_name': region, 'cells': cells})

    transition_rows: list[dict[str, Any]] = []
    for stage in stages:
        stage_name = str(stage.get('name') or '')
        explicit_active = [region for region in regions if _state_from_stage(stage, region) == 'active']
        explicit_inactive = [region for region in regions if _state_from_stage(stage, region) == 'inactive']
        effective_active = [region for region in regions if effective_lookup.get((stage_name, region)) == 'active']
        effective_inactive = [region for region in regions if effective_lookup.get((stage_name, region)) == 'inactive']
        transition_rows.append({
            'stage_name': stage_name,
            'predecessor': stage.get('predecessor'),
            'explicit_active_count': len(explicit_active),
            'explicit_inactive_count': len(explicit_inactive),
            'effective_active_count': len(effective_active),
            'effective_inactive_count': len(effective_inactive),
            'load_count': int(stage.get('load_count', 0) or 0),
            'boundary_condition_count': int(stage.get('boundary_condition_count', 0) or 0),
        })

    return {
        'stage_columns': [str(stage.get('name') or '') for stage in stages],
        'stage_matrix_rows': rows,
        'transition_rows': transition_rows,
        'explicit_cell_count': explicit_cell_count,
        'inherited_cell_count': inherited_cell_count,
        'conflict_cells': conflict_cells,
        'state_counts': state_counts,
        'has_matrix': bool(stages and regions),
    }


def _build_model_issues(
    *,
    blocks: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    regions: list[str],
    materials: list[str],
    unbound_blocks: list[dict[str, Any]],
    split_planner: dict[str, Any],
    mesh_controls: dict[str, Any],
    geometry_state: Any,
    stage_matrix: dict[str, Any],
    block_topology: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not blocks:
        issues.append(_issue('model.no_blocks', 'blocking', 'No blocks are available for modeling or meshing.', target='geometry_studio', action='Create or import geometry.'))
    if blocks and not regions:
        issues.append(_issue('model.no_regions', 'blocking', 'Blocks exist but no region catalog was derived.', target='material_region_studio', action='Refresh the model browser or assign region names.'))
    if unbound_blocks:
        names = ', '.join(str(row.get('name') or '') for row in unbound_blocks[:5])
        if len(unbound_blocks) > 5:
            names += ', ...'
        issues.append(_issue(
            'model.material_unbound',
            'blocking',
            f'{len(unbound_blocks)} blocks have no material binding: {names}',
            target='material_region_studio',
            action='Bind a material to each block before meshing.',
            details={'block_names': [str(row.get('name') or '') for row in unbound_blocks]},
        ))
    if not materials:
        issues.append(_issue('model.no_materials', 'blocking', 'No material definitions are available.', target='material_region_studio', action='Add at least one material definition.'))
    if not stages:
        issues.append(_issue('model.no_stages', 'blocking', 'No construction stages are defined.', target='stage_designer', action='Add an initial stage and staged excavation stages.'))
    if stage_matrix.get('conflict_cells'):
        issues.append(_issue(
            'model.stage_conflict',
            'blocking',
            f"{len(stage_matrix.get('conflict_cells', []))} stage-region cells are both active and inactive.",
            target='stage_designer',
            action='Resolve the conflicting stage-region states.',
            details={'cells': list(stage_matrix.get('conflict_cells', []))},
        ))
    global_size = mesh_controls.get('global_size')
    if global_size in {None, ''}:
        issues.append(_issue('model.mesh_size_missing', 'blocking', 'Global mesh size is not configured.', target='mesh_readiness', action='Set a global mesh size.'))
    else:
        try:
            if float(global_size) <= 0:
                issues.append(_issue('model.mesh_size_invalid', 'blocking', 'Global mesh size must be positive.', target='mesh_readiness', action='Set a positive global mesh size.'))
        except (TypeError, ValueError):
            issues.append(_issue('model.mesh_size_invalid', 'blocking', 'Global mesh size is not numeric.', target='mesh_readiness', action='Set a numeric global mesh size.'))
    split_rows = list(split_planner.get('split_rows', []) or [])
    auto_pairs = list(split_planner.get('auto_contact_pairs', []) or [])
    configured_pairs = list(split_planner.get('configured_contact_pairs', []) or [])
    mesh_hint_rows = list(split_planner.get('mesh_hint_rows', []) or [])
    if split_rows and not auto_pairs:
        issues.append(_issue('model.split_no_contact_pairs', 'warning', 'Split definitions exist but no derived contact pairs were mapped.', target='structures_interfaces_studio', action='Inspect split definitions and sync contact pairs.'))
    if auto_pairs and not configured_pairs:
        issues.append(_issue('model.split_contacts_unsynced', 'warning', 'Derived split contact pairs are not yet written to mesh preparation.', target='structures_interfaces_studio', action='Run Sync split contact pairs.'))
    unapplied_hints = [row for row in mesh_hint_rows if row.get('current_local_mesh_size') in {None, ''}]
    if unapplied_hints:
        issues.append(_issue('model.split_mesh_hints_unapplied', 'warning', f'{len(unapplied_hints)} split mesh hints are not applied.', target='mesh_readiness', action='Apply split mesh hints.'))
    topology = dict(block_topology or {})
    topology_summary = dict(topology.get('summary', {}) or {})
    mesh_assembly_plan = dict(topology.get('mesh_assembly_plan', {}) or {})
    mesh_assembly_summary = dict(mesh_assembly_plan.get('summary', {}) or {})
    topology_issues = [dict(issue) for issue in list(topology.get('issues', []) or []) if isinstance(issue, dict)]
    for issue in topology_issues:
        issues.append(_issue(
            str(issue.get('id') or 'model.topology_issue'),
            str(issue.get('severity') or 'warning'),
            str(issue.get('message') or 'Block topology issue.'),
            target=str(issue.get('target') or 'structures_interfaces_studio'),
            action=str(issue.get('action') or 'Review block topology.'),
            details=dict(issue.get('details', {}) or {}),
        ))
    if split_rows and int(topology_summary.get('edge_count', 0) or 0) == 0:
        issues.append(_issue('model.topology_no_edges', 'warning', 'Split definitions exist but no block adjacency edges are available.', target='structures_interfaces_studio', action='Rebuild block topology from split definitions.'))
    if int(topology_summary.get('review_policy_count', 0) or 0) > 0:
        issues.append(_issue('model.topology_policy_review', 'warning', f"{int(topology_summary.get('review_policy_count', 0) or 0)} topology mesh/contact policies need review.", target='structures_interfaces_studio', action='Review topology mesh/contact policies.'))
    if int(mesh_assembly_summary.get('merge_group_override_count', 0) or 0) > 0:
        issues.append(_issue(
            'model.mesh_assembly_contact_islands',
            'info',
            f"{int(mesh_assembly_summary.get('merge_group_override_count', 0) or 0)} regions will be isolated from automatic shared-node welding for contact/interface assembly.",
            target='mesh_readiness',
            action='Review protected contact regions before final meshing.',
            details={'protected_regions': list(mesh_assembly_plan.get('protected_regions', []) or [])},
        ))
    if str(geometry_state or '').lower() in {'missing', 'error', 'invalid'}:
        issues.append(_issue('model.geometry_not_ready', 'blocking', f'Geometry state is {geometry_state}.', target='geometry_studio', action='Repair or rebuild geometry.'))
    return issues


def _issue_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    return {
        'blocking': sum(1 for issue in issues if issue.get('severity') == 'blocking'),
        'warning': sum(1 for issue in issues if issue.get('severity') == 'warning'),
        'info': sum(1 for issue in issues if issue.get('severity') == 'info'),
    }


def _next_actions_from_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        action = str(issue.get('action') or '')
        if not action or action in seen:
            continue
        seen.add(action)
        actions.append({
            'label': action,
            'target': issue.get('target'),
            'severity': issue.get('severity'),
            'issue_id': issue.get('id'),
        })
    if not any(issue.get('severity') == 'blocking' for issue in issues):
        actions.append({'label': 'Proceed to Solve validation', 'target': 'solve', 'severity': 'info', 'issue_id': 'model.ready_for_solve'})
    return actions


def build_layout_contract() -> dict[str, Any]:
    """Return the stable v5 shell layout contract consumed by GUI and tests."""
    return {
        'version': 'v5.0',
        'primary_spaces': list(PRIMARY_SPACES),
        'regions': [
            _section('top_navigation', 'Top Navigation', 'project context, active case state, primary spaces'),
            _section('navigator', 'Navigator', 'project/model/stage/results tree switching'),
            _section('primary_workspace', 'Primary Workspace', 'workflow board, scene canvas, solve board, results canvas, delivery preview'),
            _section('context_inspector', 'Context Inspector', 'selected object and current step properties'),
            _section('system_console', 'System Console', 'alerts, runtime log, jobs, validation'),
        ],
        'system_console_tabs': list(SYSTEM_CONSOLE_TABS),
        'invariants': [
            'Exactly one formal workbench payload is produced for a document.',
            'Primary navigation is limited to Project, Model, Solve, Results, Diagnostics, Delivery.',
            'The right inspector follows the current selection instead of opening floating object panels.',
            'The bottom console owns alerts, runtime log, jobs, and validation feedback.',
        ],
    }


def build_model_space_contract() -> dict[str, Any]:
    """Return the Phase-C Model domain contract."""
    return {
        'version': 'v5.1-phase-c-hardening',
        'domain': 'model',
        'studios': [
            _section('geometry_studio', 'Geometry Studio', 'parametric geometry, block split tools, scene preview'),
            _section('material_region_studio', 'Material & Region Studio', 'region catalog, material binding, coverage audit'),
            _section('structures_interfaces_studio', 'Structures & Interfaces Studio', 'support objects, interfaces, split-derived contacts'),
            _section('stage_designer', 'Stage Designer', 'timeline, inherited stage matrix, stage scene overlay'),
            _section('mesh_readiness', 'Mesh Readiness', 'mesh controls, split mesh hints, contact readiness, blocking issues'),
        ],
        'diagnostics': {
            'issue_severities': ['blocking', 'warning', 'info'],
            'issue_targets': list(MODEL_STUDIOS),
            'next_action_contract': ['label', 'target', 'severity', 'issue_id'],
        },
        'invariants': [
            'Scene interaction is the primary path; tables are batch-edit helpers.',
            'Selection, material binding, stage activation, contact mapping, and mesh readiness share one model payload.',
            'Block split definitions must expose derived contact pairs and mesh hints before solve readiness.',
            'Stage matrix cells must expose both explicit and inherited effective states.',
            'Mesh readiness must provide blocking issues and next actions before entering Solve.',
        ],
    }


def build_results_space_contract() -> dict[str, Any]:
    """Return the Phase-D Results domain contract."""
    return {
        'version': 'v5.2-phase-d-results',
        'domain': 'results',
        'subspaces': [
            _section('stage_browser', 'Stage Browser', 'stage-wise field availability, stage status, field matrix'),
            _section('field_compare', 'Field Compare', 'selected field, compare target, stage/field comparison controls'),
            _section('result_audit', 'Result Audit', 'stage completeness, missing/partial/failed outputs, asset consistency'),
            _section('export_delivery', 'Export & Delivery Bridge', 'delivery readiness, runtime bundle and delivery targets'),
        ],
        'audit': {
            'issue_severities': ['blocking', 'warning', 'runtime_failure', 'export_failure', 'info'],
            'completeness_states': ['empty', 'partial', 'failed', 'complete'],
            'required_rows': ['stage_audit_rows', 'issues', 'issue_counts', 'next_actions'],
        },
        'invariants': [
            'Result browsing and delivery readiness must be separated but connected by one payload.',
            'Every stage result row must expose whether it is expected, present, complete, partial, or failed.',
            'Field comparison must state whether the selected field exists in both selected and compare stages.',
            'Result audit must expose next actions before a delivery package is built.',
        ],
    }


def build_delivery_space_contract() -> dict[str, Any]:
    """Return the Phase-D Delivery domain contract."""
    return {
        'version': 'v5.2-phase-d-delivery',
        'domain': 'delivery',
        'sections': [
            _section('package_manifest', 'Package Manifest', 'case snapshot, runtime bundle, recovery assets, reports'),
            _section('delivery_audit', 'Delivery Audit', 'missing package assets, result completeness, archive/manifest health'),
            _section('export_center', 'Export Center', 'package, archive, report and recovery export actions'),
            _section('lineage_center', 'Lineage Center', 'case, runtime, result and environment lineage metadata'),
        ],
        'minimum_assets': [
            'case_snapshot',
            'readiness_summary',
            'compile_report',
            'runtime_summary',
            'checkpoint_manifest',
            'result_manifest',
            'environment_summary',
            'lineage_metadata',
        ],
        'invariants': [
            'Delivery center consumes result audit instead of assuming every result database is complete.',
            'Package, archive, report preview, recovery assets, and lineage metadata are visible in one payload.',
            'Delivery audit must distinguish missing assets from export failures.',
        ],
    }


def build_solve_space_contract() -> dict[str, Any]:
    """Return the Phase-B Solve domain contract."""
    return {
        'version': 'v5.0-phase-b',
        'domain': 'solve',
        'panels': [
            _section('ready_gate', 'Ready Gate', 'validation, preprocess, compile readiness'),
            _section('run_control', 'Run Control', 'compile, run, resume, retry, abort, export controls'),
            _section('runtime_board', 'Runtime Board', 'stage, increment, residual, cutback, partition, checkpoint telemetry'),
            _section('recovery_panel', 'Recovery Panel', 'checkpoint selection, bundle health, recommended resume command'),
        ],
        'invariants': [
            'Readiness, execution, runtime monitoring, and recovery are visible in one solve payload.',
            'Recovery is an explicit user-facing operation instead of a hidden runtime detail.',
        ],
    }


def build_v5_workspace_contract() -> dict[str, Any]:
    """Return the full v5 workbench contract with Phase A/B/C domains."""
    return {
        'version': 'v5.1.1',
        'layout': build_layout_contract(),
        'model_space': build_model_space_contract(),
        'solve_space': build_solve_space_contract(),
        'primary_spaces': list(PRIMARY_SPACES),
        'results_space': build_results_space_contract(),
        'delivery_space': build_delivery_space_contract(),
        'phase_status': {
            'phase_a': 'implemented-contract',
            'phase_b': 'implemented-contract',
            'phase_c': 'block-topology-contact-policy-loop',
            'phase_d': 'results-delivery-audit-loop',
            'phase_e': 'pending-expert-console-deepening',
        },
    }


def build_solve_space_payload(solve: dict[str, Any], runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize existing SolvePresenter and RuntimePresenter output into v5 panels."""
    runtime = dict(runtime or {})
    ready_gate = dict(solve.get('ready_gate', {}) or {})
    engine_panel = dict(solve.get('engine_panel', {}) or {})
    recovery = dict(solve.get('recovery', {}) or {})
    recovery_panel = dict(solve.get('recovery_panel', {}) or {})
    recovery_controls = dict(solve.get('recovery_controls', {}) or {})
    run_control = {
        'can_validate': True,
        'can_preprocess': True,
        'can_compile': bool(ready_gate.get('validation_ok', False) or solve.get('can_compile', False)),
        'can_run': bool(ready_gate.get('validation_ok', False) or solve.get('can_run', False)),
        'can_resume': bool(recovery.get('resume_checkpoint_id') or recovery_controls.get('can_apply_recommended_recovery') or recovery_panel.get('recommended_checkpoint_id')),
        'current_profile': engine_panel.get('current_profile') or engine_panel.get('execution_profile') or 'auto',
        'engine_panel': engine_panel,
        'actions': [
            {'key': 'validate', 'label': 'Validate'},
            {'key': 'compile', 'label': 'Compile'},
            {'key': 'run', 'label': 'Run'},
            {'key': 'resume', 'label': 'Resume'},
            {'key': 'export_report', 'label': 'Export report'},
        ],
    }
    runtime_board = {
        'telemetry_available': bool(runtime or solve.get('telemetry_summary')),
        'runtime': runtime,
        'telemetry_summary': dict(solve.get('telemetry_summary', {}) or {}),
        'engine_panel': engine_panel,
        'compile_report_available': bool(solve.get('compile_report_available') or solve.get('compile_report')),
        'checkpoint_count': int(solve.get('checkpoint_count', 0) or 0),
        'latest_checkpoint_id': solve.get('latest_checkpoint_id') or recovery.get('resume_checkpoint_id'),
    }
    normalized_recovery_panel = {
        **recovery_panel,
        'recovery': recovery,
        'controls': recovery_controls,
        'selected_checkpoint_id': recovery.get('resume_checkpoint_id') or recovery_panel.get('selected_checkpoint_id'),
        'resume_mode': recovery.get('resume_mode') or recovery_panel.get('resume_mode'),
        'resume_source': recovery.get('resume_source') or recovery_panel.get('resume_source'),
    }
    return {
        'contract': build_solve_space_contract(),
        'ready_gate': ready_gate,
        'run_control': run_control,
        'runtime_board': runtime_board,
        'recovery_panel': normalized_recovery_panel,
        'summary_cards': [
            {'label': 'Ready', 'value': 'yes' if ready_gate.get('validation_ok') else 'attention'},
            {'label': 'Profile', 'value': run_control['current_profile']},
            {'label': 'Resume', 'value': 'available' if run_control['can_resume'] else 'none'},
            {'label': 'Telemetry', 'value': 'available' if runtime_board['telemetry_available'] else 'pending'},
        ],
    }


def build_model_space_payload(model: dict[str, Any]) -> dict[str, Any]:
    """Normalize ModelPresenter output into the Phase-C five-studio payload."""
    geometry_editor = dict(model.get('geometry_editor', {}) or {})
    editable_geometry = dict(geometry_editor.get('editable_geometry', {}) or {})
    editable_block_rows = _as_dict_rows(geometry_editor.get('editable_block_rows', editable_geometry.get('block_rows', [])))
    editable_block_inspector = dict(model.get('editable_block_inspector', {}) or {})
    engineering_object_palette = dict(model.get('engineering_object_palette', {}) or {})
    editable_structure_rows = _as_dict_rows(model.get('editable_structure_rows', engineering_object_palette.get('structure_rows', [])))
    editable_boundary_rows = _as_dict_rows(model.get('editable_boundary_rows', engineering_object_palette.get('boundary_rows', [])))
    editable_load_rows = _as_dict_rows(model.get('editable_load_rows', engineering_object_palette.get('load_rows', [])))
    sketch_point_rows = _as_dict_rows(model.get('sketch_point_rows', engineering_object_palette.get('sketch_point_rows', [])))
    sketch_line_rows = _as_dict_rows(model.get('sketch_line_rows', engineering_object_palette.get('sketch_line_rows', [])))
    split_planner = dict(model.get('split_planner', {}) or {})
    contact_readiness = dict(model.get('contact_readiness', {}) or {})
    interface_materialization_requests = dict(model.get('interface_materialization_requests', {}) or {})
    stage_interface_activation_plan = dict(model.get('stage_interface_activation_plan', {}) or {})
    block_topology = dict(model.get('block_topology', {}) or {})
    mesh_assembly_plan = dict(block_topology.get('mesh_assembly_plan', {}) or {})
    stage_designer = dict(model.get('stage_designer', {}) or {})
    blocks = _as_dict_rows(model.get('blocks', []))
    stages = _as_dict_rows(model.get('stages', []))
    regions = _as_str_list(model.get('region_catalog', []))
    materials = _as_str_list(model.get('materials_catalog', []))
    unbound_blocks = [row for row in blocks if not str(row.get('material_name') or '')]
    material_binding_rows = [
        {
            'block_name': str(row.get('name') or ''),
            'region_name': row.get('region_name'),
            'material_name': row.get('material_name'),
            'bound': bool(str(row.get('material_name') or '')),
            'visible': bool(row.get('visible', True)),
            'locked': bool(row.get('locked', False)),
        }
        for row in blocks
    ]
    stage_matrix = _build_stage_matrix(stages, regions)
    structures_interfaces = {
        'structure_count': int(model.get('structure_count', 0) or 0),
        'interface_count': int(model.get('interface_count', 0) or 0),
        'interface_element_count': int(model.get('interface_element_count', 0) or 0),
        'configured_contact_pairs': list(split_planner.get('configured_contact_pairs', []) or []),
        'auto_contact_pairs': list(split_planner.get('auto_contact_pairs', []) or []),
        'contact_pair_editor': dict(split_planner.get('contact_pair_editor', {}) or {}),
    }
    mesh_controls = dict(model.get('mesh_controls', {}) or {})
    issues = _build_model_issues(
        blocks=blocks,
        stages=stages,
        regions=regions,
        materials=materials,
        unbound_blocks=unbound_blocks,
        split_planner=split_planner,
        mesh_controls=mesh_controls,
        geometry_state=model.get('geometry_state'),
        stage_matrix=stage_matrix,
        block_topology=block_topology,
    )
    request_summary = dict(interface_materialization_requests.get('summary', {}) or {})
    if int(request_summary.get('manual_review_count', 0) or 0) > 0:
        issues.append(_issue(
            'model.interface_request_review',
            'warning',
            f"{int(request_summary.get('manual_review_count', 0) or 0)} interface materialization requests need review.",
            target='structures_interfaces_studio',
            action='Review interface materialization requests.',
            details={'summary': request_summary},
        ))
    if int(request_summary.get('face_interface_element_count', 0) or 0) > 0 and int(model.get('interface_element_count', 0) or 0) == 0:
        issues.append(_issue(
            'model.interface_elements_requested_empty',
            'warning',
            'Face interface element requests exist, but no interface elements are currently materialized.',
            target='mesh_readiness',
            action='Run preprocessing with interface_element_mode=policy or explicit.',
            details={'summary': request_summary},
        ))
    if str(geometry_editor.get('source_kind') or '') != 'editable_blocks':
        issues.append(_issue(
            'model.geometry_not_editable_blocks',
            'warning',
            'Current geometry source is not an editable block model.',
            target='geometry_studio',
            action='Convert to editable blocks before manual FE modeling.',
            details={'source_kind': geometry_editor.get('source_kind')},
        ))
    elif not editable_block_rows:
        issues.append(_issue(
            'model.editable_blocks_empty',
            'blocking',
            'Editable block geometry has no block definitions.',
            target='geometry_studio',
            action='Add at least one editable block.',
        ))
    if editable_block_rows and not editable_boundary_rows:
        issues.append(_issue(
            'model.no_boundary_conditions',
            'warning',
            'Editable geometry has no boundary condition definitions yet.',
            target='structures_interfaces_studio',
            action='Add at least one fixity or support boundary before solving.',
        ))
    if editable_block_rows and not editable_load_rows:
        issues.append(_issue(
            'model.no_stage_loads',
            'info',
            'No stage loads are defined. This is acceptable for pure excavation activation checks, but most FE analyses need gravity or external loads.',
            target='stage_designer',
            action='Add gravity/self-weight or stage-specific loads when needed.',
        ))
    issue_counts = _issue_counts(issues)
    blocking_issues = [issue for issue in issues if issue.get('severity') == 'blocking']
    warning_issues = [issue for issue in issues if issue.get('severity') == 'warning']
    next_actions = _next_actions_from_issues(issues)
    ready_for_solve = not blocking_issues
    coverage_percent = 100.0 if not blocks else round(100.0 * (len(blocks) - len(unbound_blocks)) / len(blocks), 2)
    unapplied_hints = [row for row in list(split_planner.get('mesh_hint_rows', []) or []) if row.get('current_local_mesh_size') in {None, ''}]
    diagnostics = {
        'issues': issues,
        'issue_rows': issues,
        'issue_counts': issue_counts,
        'blocking_issues': blocking_issues,
        'warning_issues': warning_issues,
        'next_actions': next_actions,
        'ready_for_solve': ready_for_solve,
    }
    return {
        'contract': build_model_space_contract(),
        'geometry_studio': {
            'scene_preview': dict(model.get('scene_preview', {}) or {}),
            'geometry_state': model.get('geometry_state'),
            'geometry_editor': geometry_editor,
            'editable_geometry': editable_geometry,
            'editable_block_inspector': editable_block_inspector,
            'editable_block_rows': editable_block_rows,
            'editable_block_count': len(editable_block_rows),
            'can_convert_to_editable_blocks': bool(geometry_editor.get('can_convert_to_editable_blocks')),
            'can_add_editable_block': bool(geometry_editor.get('can_add_editable_block')),
            'can_duplicate_editable_block': bool(geometry_editor.get('can_duplicate_editable_block')),
            'can_remove_editable_block': bool(geometry_editor.get('can_remove_editable_block')),
            'can_split_editable_block': bool(geometry_editor.get('can_split_editable_block')),
            'can_undo_geometry_edit': bool(geometry_editor.get('can_undo_geometry_edit')),
            'block_editor': dict(model.get('block_editor', {}) or {}),
            'split_planner': split_planner,
            'block_topology': block_topology,
            'topology_summary': dict(block_topology.get('summary', {}) or {}),
            'selection': dict(model.get('selection', {}) or {}),
            'status_cards': [
                {'label': 'Geometry state', 'value': model.get('geometry_state')},
                {'label': 'Blocks', 'value': len(blocks)},
                {'label': 'Split definitions', 'value': len(list(split_planner.get('split_rows', []) or []))},
                {'label': 'Editable blocks', 'value': len(editable_block_rows)},
                {'label': 'BCs', 'value': len(editable_boundary_rows)},
                {'label': 'Loads', 'value': len(editable_load_rows)},
                {'label': 'Editable structures', 'value': len(editable_structure_rows)},
                {'label': 'Sketch points', 'value': len(sketch_point_rows)},
                {'label': 'Sketch lines', 'value': len(sketch_line_rows)},
                {'label': 'Edit history', 'value': editable_geometry.get('history_count', 0)},
            ],
        },
        'material_region_studio': {
            'materials_catalog': materials,
            'region_catalog': regions,
            'binding_rows': material_binding_rows,
            'bound_block_count': len(blocks) - len(unbound_blocks),
            'unbound_block_count': len(unbound_blocks),
            'unbound_block_names': [str(row.get('name') or '') for row in unbound_blocks],
            'coverage_percent': coverage_percent,
            'coverage_ok': len(unbound_blocks) == 0 and bool(blocks),
        },
        'structures_interfaces_studio': {
            **structures_interfaces,
            'engineering_object_palette': engineering_object_palette,
            'editable_structure_rows': editable_structure_rows,
            'editable_boundary_rows': editable_boundary_rows,
            'editable_load_rows': editable_load_rows,
            'sketch_point_rows': sketch_point_rows,
            'sketch_line_rows': sketch_line_rows,
            'sketch_point_count': len(sketch_point_rows),
            'sketch_line_count': len(sketch_line_rows),
            'structure_editor_count': len(editable_structure_rows),
            'boundary_editor_count': len(editable_boundary_rows),
            'load_editor_count': len(editable_load_rows),
            'two_point_modeling_ready': len(sketch_point_rows) >= 2 or any(str(row.get('kind') or '') == 'two_point_nearest' for row in editable_structure_rows),
            'block_topology': block_topology,
            'adjacency_rows': list(block_topology.get('adjacency_rows', []) or []),
            'mesh_policy_rows': list(block_topology.get('mesh_policy_rows', []) or []),
            'topology_summary': dict(block_topology.get('summary', {}) or {}),
            'mesh_assembly_plan': mesh_assembly_plan,
            'mesh_assembly_summary': dict(mesh_assembly_plan.get('summary', {}) or {}),
            'interface_materialization_requests': interface_materialization_requests,
            'interface_request_rows': list(interface_materialization_requests.get('request_rows', []) or []),
            'interface_request_summary': dict(interface_materialization_requests.get('summary', {}) or {}),
            'stage_interface_activation_plan': stage_interface_activation_plan,
            'stage_interface_rows': list(stage_interface_activation_plan.get('stage_rows', []) or []),
            'stage_interface_summary': dict(stage_interface_activation_plan.get('summary', {}) or {}),
            'protected_contact_regions': list(mesh_assembly_plan.get('protected_regions', []) or []),
            'unsynced_auto_contact_pair_count': 0 if structures_interfaces['configured_contact_pairs'] else len(structures_interfaces['auto_contact_pairs']),
            'contact_sync_ready': bool(structures_interfaces['auto_contact_pairs']),
        },
        'stage_designer': {
            **stage_designer,
            'stage_rows': stages,
            'stage_matrix_rows': stage_matrix['stage_matrix_rows'],
            'stage_columns': stage_matrix['stage_columns'],
            'transition_rows': stage_matrix['transition_rows'],
            'stage_count': len(stages),
            'region_count': len(regions),
            'explicit_cell_count': stage_matrix['explicit_cell_count'],
            'inherited_cell_count': stage_matrix['inherited_cell_count'],
            'conflict_cells': stage_matrix['conflict_cells'],
            'state_counts': stage_matrix['state_counts'],
            'has_timeline': bool(stages),
            'has_matrix': stage_matrix['has_matrix'],
            'has_scene_overlay': bool(stages and blocks),
        },
        'mesh_readiness': {
            'mesh_controls': mesh_controls,
            'contact_readiness': contact_readiness,
            'mesh_hint_rows': list(split_planner.get('mesh_hint_rows', []) or []),
            'adjacency_rows': list(block_topology.get('adjacency_rows', []) or []),
            'mesh_policy_rows': list(block_topology.get('mesh_policy_rows', []) or []),
            'topology_summary': dict(block_topology.get('summary', {}) or {}),
            'mesh_assembly_plan': mesh_assembly_plan,
            'mesh_assembly_summary': dict(mesh_assembly_plan.get('summary', {}) or {}),
            'interface_materialization_requests': interface_materialization_requests,
            'interface_request_rows': list(interface_materialization_requests.get('request_rows', []) or []),
            'interface_request_summary': dict(interface_materialization_requests.get('summary', {}) or {}),
            'stage_interface_activation_plan': stage_interface_activation_plan,
            'stage_interface_rows': list(stage_interface_activation_plan.get('stage_rows', []) or []),
            'stage_interface_summary': dict(stage_interface_activation_plan.get('summary', {}) or {}),
            'protected_contact_regions': list(mesh_assembly_plan.get('protected_regions', []) or []),
            'merge_group_overrides': dict(mesh_assembly_plan.get('merge_group_overrides', {}) or {}),
            'interface_materialization_requests': interface_materialization_requests,
            'interface_request_rows': list(interface_materialization_requests.get('request_rows', []) or []),
            'interface_request_summary': dict(interface_materialization_requests.get('summary', {}) or {}),
            'stage_interface_activation_plan': stage_interface_activation_plan,
            'stage_interface_rows': list(stage_interface_activation_plan.get('stage_rows', []) or []),
            'stage_interface_summary': dict(stage_interface_activation_plan.get('summary', {}) or {}),
            'unapplied_mesh_hint_count': len(unapplied_hints),
            'blocking_issues': blocking_issues,
            'warning_issues': warning_issues,
            'issue_rows': issues,
            'issue_counts': issue_counts,
            'next_actions': next_actions,
            'ready_for_solve': ready_for_solve,
            'can_enter_solve': ready_for_solve,
        },
        'diagnostics': diagnostics,
        'summary_cards': [
            {'label': 'Blocks', 'value': len(blocks)},
            {'label': 'Materials', 'value': len(materials)},
            {'label': 'Stages', 'value': len(stages)},
            {'label': 'Material coverage', 'value': f'{coverage_percent:.1f}%'},
            {'label': 'Model issues', 'value': f"{issue_counts['blocking']} blocking / {issue_counts['warning']} warnings"},
            {'label': 'Mesh readiness', 'value': 'ready' if ready_for_solve else 'blocked'},
            {'label': 'Contact islands', 'value': int(dict(mesh_assembly_plan.get('summary', {}) or {}).get('protected_region_count', 0) or 0)},
            {'label': 'Interface requests', 'value': int(dict(interface_materialization_requests.get('summary', {}) or {}).get('request_count', 0) or 0)},
            {'label': 'Editable blocks', 'value': len(editable_block_rows)},
            {'label': 'BCs', 'value': len(editable_boundary_rows)},
            {'label': 'Loads', 'value': len(editable_load_rows)},
            {'label': 'Editable structures', 'value': len(editable_structure_rows)},
        ],
    }
