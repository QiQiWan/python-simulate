from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from geoai_simkit.geometry.dirty_state import summarize_dirty_state
from geoai_simkit.geometry.workflow_audit import audit_geometry_workflow
from geoai_simkit.geometry.geometry_readiness import build_plaxis_gap_analysis
from geoai_simkit.geometry.editable_blocks import build_editable_geometry_payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _severity_rank(severity: str) -> int:
    order = {"ok": 0, "info": 1, "warning": 2, "error": 3, "blocked": 4}
    return order.get(str(severity or "info"), 1)


def _dedupe_notifications(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        key = str(item.get("id") or item.get("message") or item.get("title") or len(out))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda item: _severity_rank(str(item.get("severity", "info"))), reverse=True)
    return out


@dataclass(slots=True)
class ModernWorkspaceStateBuilder:
    """Builds a product-level UX state contract without requiring a live Qt session.

    The contract keeps the UI modern and predictable: one status bar, one command
    palette, one notification center, and one solve-readiness gate.  It deliberately
    does not edit meshes directly; mesh actions are always regenerated from source
    entities.
    """

    parameters: dict[str, Any]
    case_name: str = "Untitled"
    active_space: str = "model"
    active_view: str = "scene"
    messages: Iterable[str] = field(default_factory=tuple)
    document_dirty: bool = False
    file_path: str | None = None
    model_metadata: dict[str, Any] | None = None

    def build(self) -> dict[str, Any]:
        parameters = dict(self.parameters or {})
        dirty = summarize_dirty_state(parameters)
        payload = build_editable_geometry_payload(parameters)
        workflow = audit_geometry_workflow(parameters, model_metadata=self.model_metadata or {})
        gap = build_plaxis_gap_analysis(parameters, model_payload=payload)
        selected = dict(parameters.get("selected_topology_entity") or {})
        selected_id = str(selected.get("entity_id") or parameters.get("selected_entity_id") or "")
        notifications = self._build_notifications(dirty, workflow, gap, selected_id)
        gate = self._build_solve_gate(dirty, workflow, gap, notifications)
        commands = self._build_command_palette(dirty, gate, selected_id)
        status = self._build_status_bar(dirty, gate, notifications, selected_id)
        timeline = self._build_timeline(parameters)
        return {
            "contract": "modern_workspace_state_v1",
            "generated_at": _utc_now(),
            "case_name": self.case_name,
            "active_space": self.active_space,
            "active_view": self.active_view,
            "file_path": self.file_path,
            "document_dirty": bool(self.document_dirty),
            "status_bar": status,
            "notification_center": {
                "contract": "notification_center_v1",
                "unread_count": len([n for n in notifications if str(n.get("severity")) in {"warning", "error", "blocked"}]),
                "items": notifications,
            },
            "command_palette": {
                "contract": "command_palette_v1",
                "placeholder": "Search commands, modeling tools, checks, and exports...",
                "commands": commands,
                "shortcut_hint": "Ctrl/⌘ + K",
            },
            "solve_readiness_gate": gate,
            "workflow_timeline": timeline,
            "selection_hud": self._build_selection_hud(selected_id, parameters),
            "autosave_recovery": self._build_autosave_recovery(parameters),
            "operation_history": self._build_operation_history(parameters),
            "empty_state": self._build_empty_state(payload),
            "accessibility": {
                "keyboard_shortcuts": [
                    {"keys": "Ctrl/⌘+K", "action": "Open command palette"},
                    {"keys": "Esc", "action": "Clear active selection"},
                    {"keys": "Shift+Drag", "action": "Box select entities"},
                    {"keys": "G", "action": "Toggle transform gizmo"},
                    {"keys": "R", "action": "Regenerate mesh from entities"},
                ],
                "high_contrast_ready": True,
                "screen_reader_labels": True,
            },
        }

    def _build_notifications(self, dirty: dict[str, Any], workflow: dict[str, Any], gap: dict[str, Any], selected_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if dirty.get("requires_remesh"):
            rows.append({"id": "mesh_stale", "severity": "warning", "title": "Mesh is stale", "message": "Source entities changed. Regenerate the mesh before solving.", "action": "regenerate_mesh"})
        if dirty.get("requires_resolve"):
            rows.append({"id": "results_stale", "severity": "warning", "title": "Results are stale", "message": "Previous results do not match the latest geometry or mesh.", "action": "clear_or_resolve"})
        wf_items = list(workflow.get("items", []) or workflow.get("checks", []) or [])
        for idx, item in enumerate(wf_items[:12]):
            status = str(item.get("status") or item.get("severity") or "")
            if status.lower() in {"fail", "failed", "blocked", "error", "warning"}:
                rows.append({
                    "id": f"workflow_{idx}_{item.get('id', item.get('name', 'check'))}",
                    "severity": "blocked" if status.lower() in {"fail", "failed", "blocked", "error"} else "warning",
                    "title": str(item.get("label") or item.get("name") or "Workflow check"),
                    "message": str(item.get("message") or item.get("action") or "Review this modeling check."),
                    "action": str(item.get("action") or "review_workflow_audit"),
                })
        gap_rows = list(gap.get("rows", []) or gap.get("items", []) or [])
        for idx, item in enumerate(gap_rows[:12]):
            status = str(item.get("status") or "")
            if status.lower() in {"missing", "partial", "blocked", "warning"}:
                rows.append({
                    "id": f"gap_{idx}_{item.get('area', 'area')}_{item.get('item', 'item')}",
                    "severity": "warning" if status.lower() != "blocked" else "blocked",
                    "title": str(item.get("item") or "PLAXIS-like workflow gap"),
                    "message": str(item.get("action") or item.get("evidence") or "Complete this item to improve GUI modeling readiness."),
                    "action": str(item.get("action_key") or "open_plaxis_gap_analysis"),
                })
        for idx, msg in enumerate(list(self.messages)[-5:]):
            rows.append({"id": f"recent_message_{idx}", "severity": "info", "title": "Recent action", "message": str(msg), "action": "open_console"})
        if selected_id:
            rows.append({"id": "selection_active", "severity": "info", "title": "Entity selected", "message": selected_id, "action": "open_selection_inspector"})
        return _dedupe_notifications(rows)

    def _build_solve_gate(self, dirty: dict[str, Any], workflow: dict[str, Any], gap: dict[str, Any], notifications: list[dict[str, Any]]) -> dict[str, Any]:
        blockers = [n for n in notifications if str(n.get("severity")) in {"blocked", "error"}]
        warnings = [n for n in notifications if str(n.get("severity")) == "warning"]
        ready = not blockers and not dirty.get("requires_remesh")
        next_action = "solve" if ready else ("regenerate_mesh" if dirty.get("requires_remesh") else (str(blockers[0].get("action")) if blockers else "review_warnings"))
        return {
            "contract": "modern_solve_readiness_gate_v1",
            "ready_to_solve": bool(ready),
            "severity": "ok" if ready else ("blocked" if blockers or dirty.get("requires_remesh") else "warning"),
            "blocker_count": len(blockers) + (1 if dirty.get("requires_remesh") else 0),
            "warning_count": len(warnings),
            "next_action": next_action,
            "primary_label": "Run solver" if ready else ("Regenerate mesh" if next_action == "regenerate_mesh" else "Review pre-solve checks"),
            "audit_contract": workflow.get("contract"),
            "gap_contract": gap.get("contract"),
            "mesh_is_generated_artifact": True,
            "mesh_editable": False,
        }

    def _command(self, key: str, label: str, group: str, enabled: bool, *, shortcut: str = "", reason: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"id": key, "label": label, "group": group, "enabled": bool(enabled), "shortcut": shortcut, "disabled_reason": "" if enabled else reason, "payload": dict(payload or {})}

    def _build_command_palette(self, dirty: dict[str, Any], gate: dict[str, Any], selected_id: str) -> list[dict[str, Any]]:
        selected = bool(selected_id)
        return [
            self._command("regenerate_mesh", "Regenerate mesh from source entities", "Modeling", bool(dirty.get("requires_remesh")), shortcut="R", reason="Mesh is already current."),
            self._command("run_pre_solve_check", "Run geometry pre-solve check", "Solve", True, shortcut="Ctrl+Shift+C"),
            self._command("run_solver", "Run solver", "Solve", bool(gate.get("ready_to_solve")), shortcut="Ctrl+Enter", reason="Resolve blockers in the pre-solve gate first."),
            self._command("open_selection_inspector", "Open selection inspector", "Inspect", selected, shortcut="I", reason="Select a face, solid, or named selection first.", payload={"entity_id": selected_id}),
            self._command("create_named_selection", "Create named selection from viewport", "Modeling", selected, shortcut="N", reason="No viewport selection."),
            self._command("apply_component_parameters", "Apply component parameters", "Modeling", True),
            self._command("review_binding_transfer", "Review migrated entity bindings", "Modeling", True),
            self._command("preview_face_load_direction", "Preview selected face-load direction", "Loads", selected, reason="Select a face set first."),
            self._command("open_quality_report", "Open mesh quality report", "Quality", True),
            self._command("save_project", "Save project", "Project", True, shortcut="Ctrl+S"),
            self._command("save_project_as", "Save project as...", "Project", True),
            self._command("export_result_package", "Export result package", "Delivery", True),
        ]

    def _build_status_bar(self, dirty: dict[str, Any], gate: dict[str, Any], notifications: list[dict[str, Any]], selected_id: str) -> dict[str, Any]:
        return {
            "contract": "modern_status_bar_v1",
            "case_name": self.case_name,
            "dirty": bool(self.document_dirty),
            "mesh_status": "stale" if dirty.get("requires_remesh") else "current_or_not_generated",
            "result_status": "stale" if dirty.get("requires_resolve") else "current_or_not_generated",
            "solve_status": "ready" if gate.get("ready_to_solve") else "blocked",
            "selected_entity_id": selected_id,
            "notification_count": len(notifications),
            "primary_next_action": gate.get("next_action"),
        }

    def _build_selection_hud(self, selected_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        bindings = dict(parameters.get("topology_entity_bindings", {}) or {}).get(selected_id, {}) if selected_id else {}
        return {
            "contract": "selection_hud_v1",
            "visible": bool(selected_id),
            "entity_id": selected_id,
            "bindings": bindings if isinstance(bindings, dict) else {},
            "primary_actions": ["inspect", "assign_material", "add_boundary", "add_stage_load", "set_mesh_size", "create_named_selection"] if selected_id else [],
        }

    def _build_timeline(self, parameters: dict[str, Any]) -> dict[str, Any]:
        dirty = summarize_dirty_state(parameters)
        steps = [
            {"id": "sketch", "label": "Sketch / import geometry", "status": "done" if parameters.get("sketch_geometry") or parameters.get("blocks") or parameters.get("editable_blocks") else "current"},
            {"id": "entities", "label": "Edit entities and components", "status": "done" if parameters.get("blocks") or parameters.get("editable_blocks") else "pending"},
            {"id": "bindings", "label": "Assign materials, BCs, loads, stages", "status": "done" if parameters.get("topology_entity_bindings") else "pending"},
            {"id": "mesh", "label": "Regenerate mesh", "status": "blocked" if dirty.get("requires_remesh") else "done"},
            {"id": "check", "label": "Pre-solve check", "status": "current" if dirty.get("requires_remesh") else "done"},
            {"id": "solve", "label": "Solve", "status": "pending" if dirty.get("requires_remesh") else "current"},
        ]
        return {"contract": "modern_workflow_timeline_v1", "steps": steps}

    def _build_autosave_recovery(self, parameters: dict[str, Any]) -> dict[str, Any]:
        auto = dict(parameters.get("autosave_recovery", {}) or {})
        return {
            "contract": "autosave_recovery_status_v1",
            "enabled": bool(auto.get("enabled", True)),
            "last_autosave_id": str(auto.get("last_autosave_id", "")),
            "last_autosave_time": str(auto.get("last_autosave_time", "")),
            "recovery_available": bool(auto.get("recovery_available", False)),
            "retention": int(auto.get("retention", 10) or 10),
        }

    def _build_operation_history(self, parameters: dict[str, Any]) -> dict[str, Any]:
        history = list(parameters.get("operation_history", []) or [])
        legacy = list(parameters.get("geometry_transactions", []) or []) + list(parameters.get("component_realization_history", []) or [])
        rows = [dict(row) for row in history[-20:] if isinstance(row, dict)]
        for row in legacy[-10:]:
            if isinstance(row, dict):
                rows.append({"kind": str(row.get("contract", "legacy_transaction")), "summary": row.get("summary", row), "timestamp": row.get("timestamp", "")})
        return {"contract": "operation_history_panel_v1", "count": len(rows), "rows": rows[-30:], "undo_available": bool(parameters.get("geometry_undo_stack")), "redo_available": bool(parameters.get("geometry_redo_stack"))}

    def _build_empty_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        block_count = int(payload.get("block_count", 0) or 0)
        if block_count:
            return {"contract": "empty_state_v1", "visible": False}
        return {
            "contract": "empty_state_v1",
            "visible": True,
            "headline": "Start with a pit outline or editable blocks",
            "body": "Create a sketch, import geometry, or apply the PLAXIS-like pit workflow to generate source entities. Meshes are generated later from these entities.",
            "primary_action": "create_pit_outline_sketch",
            "secondary_actions": ["import_geometry", "load_demo_case", "apply_plaxis_like_workflow"],
        }


def build_modern_workspace_state(
    parameters: dict[str, Any],
    *,
    case_name: str = "Untitled",
    active_space: str = "model",
    active_view: str = "scene",
    messages: Iterable[str] = (),
    document_dirty: bool = False,
    file_path: str | None = None,
    model_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ModernWorkspaceStateBuilder(
        parameters=dict(parameters or {}),
        case_name=case_name,
        active_space=active_space,
        active_view=active_view,
        messages=messages,
        document_dirty=document_dirty,
        file_path=file_path,
        model_metadata=model_metadata or {},
    ).build()
