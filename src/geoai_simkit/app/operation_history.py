from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def append_operation(parameters: dict[str, Any], *, kind: str, message: str, payload: dict[str, Any] | None = None, max_items: int = 100) -> dict[str, Any]:
    params = dict(parameters or {})
    rows = [dict(row) for row in list(params.get("operation_history", []) or []) if isinstance(row, dict)]
    rows.append({
        "contract": "operation_history_item_v1",
        "kind": str(kind or "operation"),
        "message": str(message or ""),
        "payload": dict(payload or {}),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    params["operation_history"] = rows[-int(max_items):]
    return params


def push_geometry_snapshot(parameters: dict[str, Any], *, reason: str, max_items: int = 20) -> dict[str, Any]:
    params = dict(parameters or {})
    snapshot_keys = [
        "blocks", "editable_blocks", "block_splits", "named_selections", "topology_entity_bindings",
        "mesh_size_controls", "component_parameters", "sketch_geometry", "wall_offset_sketches",
    ]
    snapshot = {key: params.get(key) for key in snapshot_keys if key in params}
    undo = [dict(row) for row in list(params.get("geometry_undo_stack", []) or []) if isinstance(row, dict)]
    undo.append({"reason": str(reason or "geometry edit"), "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "snapshot": snapshot})
    params["geometry_undo_stack"] = undo[-int(max_items):]
    params["geometry_redo_stack"] = []
    return params
