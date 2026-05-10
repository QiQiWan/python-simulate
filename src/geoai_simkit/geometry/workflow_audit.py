from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geometry.dirty_state import summarize_dirty_state


@dataclass(slots=True)
class GeometryWorkflowAudit:
    readiness_score: float
    blockers: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    next_actions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'contract': 'geometry_workflow_audit_v1',
            'readiness_score': float(self.readiness_score),
            'blockers': [dict(row) for row in self.blockers],
            'warnings': [dict(row) for row in self.warnings],
            'next_actions': list(self.next_actions),
            'summary': {
                'blocker_count': len(self.blockers),
                'warning_count': len(self.warnings),
                'ready_for_solve': bool(self.readiness_score >= 0.80 and not self.blockers),
            },
            'metadata': dict(self.metadata),
        }


def audit_geometry_workflow(parameters: dict[str, Any] | None, *, model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    meta = dict(model_metadata or {})
    dirty = summarize_dirty_state(params)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    actions: list[str] = []

    if dirty.get('requires_remesh'):
        blockers.append({'id': 'geometry.mesh_stale', 'severity': 'error', 'message': 'Editable entities changed; regenerate the mesh before solving.'})
        actions.append('regenerate_mesh')
    if dirty.get('requires_resolve'):
        warnings.append({'id': 'geometry.results_stale', 'severity': 'warning', 'message': 'Results or solver package are stale after geometry/binding changes.'})
        actions.append('rerun_solver_after_remesh')

    binding_report = dict(params.get('binding_transfer_report', {}) or {})
    invalid = list(binding_report.get('invalid_bindings', []) or [])
    if invalid:
        blockers.append({'id': 'geometry.binding_transfer_invalid', 'severity': 'error', 'count': len(invalid), 'message': 'Some entity bindings no longer match current BRep/FaceSet entities.'})
        actions.append('review_binding_transfer')

    face_sets = dict(meta.get('mesh.face_sets', params.get('mesh.face_sets', {})) or {})
    fs_summary = dict(face_sets.get('summary', {}) or {})
    if int(fs_summary.get('unmatched_boundary_face_count', 0) or 0) > 0:
        warnings.append({'id': 'mesh.face_set_unmatched', 'severity': 'warning', 'count': int(fs_summary.get('unmatched_boundary_face_count', 0) or 0), 'message': 'Some physical surfaces were not matched to tetra boundary faces.'})
        actions.append('inspect_face_sets')

    quality = dict(meta.get('mesh.quality_report', params.get('mesh_quality_report', {})) or {})
    qsum = dict(quality.get('summary', {}) or {})
    if int(qsum.get('bad_cell_count', 0) or 0) > 0:
        blockers.append({'id': 'mesh.bad_cells', 'severity': 'error', 'count': int(qsum.get('bad_cell_count', 0) or 0), 'message': 'Bad tetra cells detected; adjust geometry or mesh-size fields and remesh.'})
        actions.append('review_mesh_quality')

    sketch = dict(params.get('pit_modeling', {}) or {}).get('sketch_report') or params.get('pit_outline_sketch_report') or {}
    if sketch and not bool(dict(sketch).get('ready_for_pit_modeling', False)):
        warnings.append({'id': 'pit.sketch_not_ready', 'severity': 'warning', 'message': 'Pit outline sketch is not ready for modeling.'})
        actions.append('validate_or_close_pit_sketch')

    score = 1.0
    score -= 0.22 * len(blockers)
    score -= 0.08 * len(warnings)
    score = max(0.0, min(1.0, score))
    return GeometryWorkflowAudit(score, tuple(blockers), tuple(warnings), tuple(dict.fromkeys(actions)), {'dirty_state': dirty}).to_dict()




def build_presolve_check_panel(parameters: dict[str, Any] | None, *, model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build GUI-oriented rows for the solve pre-check panel."""
    audit = audit_geometry_workflow(parameters, model_metadata=model_metadata)
    summary = dict(audit.get('summary', {}) or {})
    dirty = dict(dict(audit.get('metadata', {}) or {}).get('dirty_state', {}) or {})
    blockers = [dict(row) for row in list(audit.get('blockers', []) or [])]
    warnings = [dict(row) for row in list(audit.get('warnings', []) or [])]
    rows: list[dict[str, Any]] = []
    rows.append({'check': 'Geometry dirty state', 'status': 'stale' if dirty.get('requires_remesh') else 'current', 'message': dirty.get('reason', '') or ('Remesh required' if dirty.get('requires_remesh') else 'Mesh is current')})
    rows.append({'check': 'Binding transfer', 'status': 'blocked' if any(row.get('id') == 'geometry.binding_transfer_invalid' for row in blockers) else 'ok', 'message': 'Review invalid entity bindings after remesh.' if any(row.get('id') == 'geometry.binding_transfer_invalid' for row in blockers) else 'No invalid binding transfer rows detected.'})
    rows.append({'check': 'Face sets', 'status': 'warning' if any(row.get('id') == 'mesh.face_set_unmatched' for row in warnings) else 'ok', 'message': 'Some physical surfaces are unmatched.' if any(row.get('id') == 'mesh.face_set_unmatched' for row in warnings) else 'FaceSet matching has no reported blocker.'})
    rows.append({'check': 'Mesh quality', 'status': 'blocked' if any(row.get('id') == 'mesh.bad_cells' for row in blockers) else 'ok', 'message': 'Bad cells must be repaired before solving.' if any(row.get('id') == 'mesh.bad_cells' for row in blockers) else 'No bad cells reported.'})
    rows.append({'check': 'Pit sketch', 'status': 'warning' if any(row.get('id') == 'pit.sketch_not_ready' for row in warnings) else 'ok', 'message': 'Pit sketch is not ready.' if any(row.get('id') == 'pit.sketch_not_ready' for row in warnings) else 'Pit sketch is ready or not required.'})
    issue_rows = []
    for kind, coll in (('blocker', blockers), ('warning', warnings)):
        for row in coll:
            issue_rows.append({'kind': kind, 'id': row.get('id', ''), 'severity': row.get('severity', ''), 'message': row.get('message', ''), 'action': row.get('action', '')})
    return {
        'contract': 'pre_solve_geometry_check_panel_v1',
        'ready_for_solve': bool(summary.get('ready_for_solve', False)),
        'readiness_score': float(audit.get('readiness_score', 0.0) or 0.0),
        'check_rows': rows,
        'issue_rows': issue_rows,
        'next_actions': list(audit.get('next_actions', []) or []),
        'audit': audit,
        'summary': {'ready_for_solve': bool(summary.get('ready_for_solve', False)), 'blocker_count': len(blockers), 'warning_count': len(warnings)},
    }

__all__ = ['GeometryWorkflowAudit', 'audit_geometry_workflow', 'build_presolve_check_panel']
