from __future__ import annotations

"""Stateful point/line/surface/block creation tools for GUI viewports."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.app.viewport.snap_controller import SEMANTIC_LABELS

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent
from geoai_simkit.app.viewport.preview_overlay import message_output, preview_output
from geoai_simkit.contracts.viewport import ViewportToolOutput
from geoai_simkit.commands import CreateBlockCommand, CreateLineCommand, CreatePointCommand, CreateSurfaceCommand


def _world(event: ToolEvent) -> tuple[float, float, float]:
    return tuple(float(v) for v in (event.world or (event.x, 0.0, event.y)))  # type: ignore[return-value]


def _created_id_from_result(result: Any) -> str:
    try:
        metadata = dict(getattr(result, "metadata", {}) or {})
        value = metadata.get("id") or metadata.get("entity_id")
        if value:
            return str(value)
    except Exception:
        pass
    affected = list(getattr(result, "affected_entities", []) or [])
    return str(affected[0]) if affected else ""


def _interaction_metadata(event: ToolEvent, *, phase: str = "preview", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = dict(event.metadata.get("snap") or {}) if isinstance(event.metadata, dict) else {}
    constraint = dict(event.metadata.get("constraint") or {}) if isinstance(event.metadata, dict) else {}
    point = constraint.get("point") or snap.get("point") or list(_world(event))
    mode = str(snap.get("mode") or "none")
    snap_label = str(snap.get("snap_label") or SEMANTIC_LABELS.get(mode, ""))
    constraint_mode = str(constraint.get("mode") or "none")
    constraint_label = str(constraint.get("snap_label") or SEMANTIC_LABELS.get(constraint_mode, ""))
    constraint_meta = dict(constraint.get("metadata") or {}) if isinstance(constraint.get("metadata"), dict) else {}
    constraint_lock = dict(constraint_meta.get("lock") or {}) if isinstance(constraint_meta.get("lock"), dict) else {}
    return {
        "contract": "viewport_creation_affordance_v3",
        "phase": phase,
        "screen_space_crosshair": True,
        "crosshair_world": point,
        "snap_point": snap.get("point") or point,
        "snap_mode": mode,
        "snap_label": snap_label,
        "snapped": bool(snap.get("snapped")),
        "target_entity_id": str(snap.get("target_entity_id") or ""),
        "constraint_point": point,
        "constraint_mode": constraint_mode,
        "constraint_label": constraint_label,
        "constraint_active": bool(constraint.get("snapped")),
        "constraint_target_entity_id": str(constraint.get("target_entity_id") or ""),
        "constraint_locked": bool(constraint_meta.get("locked") or constraint_lock.get("enabled")),
        "constraint_lock": constraint_lock,
        "constraint_trail": list(constraint_lock.get("trail") or []),
        "constraint_visualization": dict(constraint_lock.get("visualization") or {}),
        **dict(extra or {}),
    }


def _normal_from_event(event: ToolEvent) -> tuple[float, float, float] | None:
    try:
        normal = event.metadata.get("normal") if isinstance(event.metadata, dict) else None
        if normal is not None and len(normal) >= 3:
            return (float(normal[0]), float(normal[1]), float(normal[2]))
    except Exception:
        pass
    return None


def _constrained_world(event: ToolEvent, context: ToolContext, anchor: tuple[float, float, float] | None, *, normal: tuple[float, float, float] | None = None) -> tuple[tuple[float, float, float], dict[str, Any]]:
    world = _world(event)
    snap_controller = None
    try:
        snap_controller = dict(context.metadata or {}).get("snap_controller")
    except Exception:
        snap_controller = None
    if snap_controller is None or not hasattr(snap_controller, "constrain"):
        return world, {}
    requested = ""
    try:
        if isinstance(event.metadata, dict):
            raw_requested = event.metadata.get("constraint_mode") or event.metadata.get("constraint_request") or ""
            if not raw_requested and isinstance(event.metadata.get("constraint"), str):
                raw_requested = event.metadata.get("constraint")
            requested = str(raw_requested or "")
    except Exception:
        requested = ""
    result = snap_controller.constrain(world, anchor=anchor, state=context.viewport, normal=normal or _normal_from_event(event), requested=requested, modifiers=event.modifiers)
    if getattr(result, "snapped", False):
        meta = result.to_dict()
        event.metadata = {**dict(event.metadata or {}), "constraint": meta}
        return tuple(float(v) for v in result.point), meta
    return world, {}



def _record_constraint_placement(context: ToolContext, point: tuple[float, float, float], *, kind: str, entity_id: str = "") -> dict[str, Any]:
    try:
        snap_controller = dict(context.metadata or {}).get("snap_controller")
    except Exception:
        snap_controller = None
    if snap_controller is None or not hasattr(snap_controller, "record_constraint_placement"):
        return {}
    try:
        return dict(snap_controller.record_constraint_placement(point, kind=kind, entity_id=entity_id) or {})
    except Exception:
        return {}

def _creation_command_output(tool: str, result: Any, *, select_kind: str, point: tuple[float, float, float] | None = None, constraint_lock: dict[str, Any] | None = None) -> ViewportToolOutput:
    entity_id = _created_id_from_result(result)
    metadata: dict[str, Any] = {
        "auto_select_created": True,
        "select_entity_id": entity_id,
        "select_kind": select_kind,
        "created_entity_id": entity_id,
        "created_kind": select_kind,
    }
    if point is not None:
        metadata["last_created_world"] = list(point)
    if constraint_lock:
        metadata["constraint_lock"] = dict(constraint_lock)
        metadata["constraint_trail"] = list(dict(constraint_lock).get("trail") or [])
        metadata["constraint_visualization"] = dict(dict(constraint_lock).get("visualization") or {})
    return ViewportToolOutput(kind="command", tool=tool, message=result.message, command_result=result.to_dict(), metadata=metadata)


class PointTool(ModelingTool):
    name = "point"

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        xyz, _constraint = _constrained_world(event, context, None)
        return preview_output(self.name, "point", [xyz], message="预览点：左键创建点；若约束已锁定，会按锁定沿边/沿法向投影", metadata=_interaction_metadata(event, extra={"tool_hint": "left_click_create_point", "constraint_lock_supported": True}))

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        x, y, z = _constrained_world(event, context, None)[0]
        result = context.command_stack.execute(CreatePointCommand(x=x, y=y, z=z), context.document)
        entity_id = _created_id_from_result(result)
        lock = _record_constraint_placement(context, (x, y, z), kind="point", entity_id=entity_id)
        return _creation_command_output(self.name, result, select_kind="point", point=(x, y, z), constraint_lock=lock)


@dataclass
class LineTool(ModelingTool):
    name: str = "line"
    pending_start: tuple[float, float, float] | None = None

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        xyz, constraint = _constrained_world(event, context, None)
        if self.pending_start is None:
            self.pending_start = xyz
            self.mode = "awaiting_end"
            return preview_output(self.name, "line", [xyz], message="已设置线起点；移动鼠标预览，左键确定终点", metadata=_interaction_metadata(event, phase="start", extra={"tool_hint": "pick_line_end"}))
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        start = self.pending_start
        xyz, constraint = _constrained_world(event, context, start)
        result = context.command_stack.execute(CreateLineCommand(start=start, end=xyz), context.document)
        entity_id = _created_id_from_result(result)
        _record_constraint_placement(context, start, kind="curve_start", entity_id=entity_id)
        lock = _record_constraint_placement(context, xyz, kind="curve_end", entity_id=entity_id)
        self.pending_start = None
        self.mode = "active"
        return _creation_command_output(self.name, result, select_kind="curve", point=xyz, constraint_lock=lock)

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        if self.pending_start is None:
            return None
        xyz, constraint = _constrained_world(event, context, self.pending_start)
        return preview_output(self.name, "line", [self.pending_start, xyz], message="预览线：左键确定终点；Shift 水平，Ctrl 垂直；锁定沿边/沿法向会连续生效；Esc 取消", metadata=_interaction_metadata(event, extra={"tool_hint": "left_click_finish_line", "constraint_available": ["horizontal", "vertical", "along_edge", "along_normal"]}))

    def on_key_press(self, key: str, context: ToolContext) -> Any:
        if str(key).lower() in {"backspace", "delete"}:
            self.pending_start = None
            self.mode = "active"
            return message_output(self.name, "Line start cleared")
        return None

    def cancel(self, context: ToolContext) -> None:
        self.pending_start = None
        self.mode = "cancelled"


@dataclass
class SurfaceTool(ModelingTool):
    name: str = "surface"
    points: list[tuple[float, float, float]] = field(default_factory=list)
    min_points: int = 3

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        if event.button == "right":
            return self.commit(context)
        anchor = self.points[-1] if self.points else None
        xyz, constraint = _constrained_world(event, context, anchor)
        self.points.append(xyz)
        self.mode = f"collecting_{len(self.points)}"
        return preview_output(self.name, "surface", self.points, closed=len(self.points) >= self.min_points, message="收集面边界点；右键打开完成/撤销/取消菜单", metadata=_interaction_metadata(event, phase="collect", extra={"point_count": len(self.points), "can_finish": len(self.points) >= self.min_points, "right_click_completion_menu": True}))

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        if not self.points:
            return None
        xyz, constraint = _constrained_world(event, context, self.points[-1])
        return preview_output(self.name, "surface", [*self.points, xyz], closed=False, message="预览面：继续左键加点；Shift/Ctrl 或锁定沿边/沿法向约束；右键完成/撤销/取消", metadata=_interaction_metadata(event, extra={"point_count": len(self.points), "can_finish": len(self.points) >= self.min_points, "right_click_completion_menu": True, "constraint_available": ["horizontal", "vertical", "along_edge", "along_normal"]}))

    def commit(self, context: ToolContext) -> Any:
        if len(self.points) < self.min_points:
            return message_output(self.name, "Surface requires at least 3 points", error=True)
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(CreateSurfaceCommand(coords=tuple(self.points)), context.document)
        entity_id = _created_id_from_result(result)
        lock = {}
        for point in self.points:
            lock = _record_constraint_placement(context, point, kind="surface_point", entity_id=entity_id)
        last_point = self.points[-1] if self.points else None
        self.points.clear()
        self.mode = "active"
        return _creation_command_output(self.name, result, select_kind="surface", point=last_point, constraint_lock=lock)

    def on_key_press(self, key: str, context: ToolContext) -> Any:
        key_l = str(key).lower()
        if key_l in {"backspace", "delete"}:
            if self.points:
                removed = self.points.pop()
                self.mode = f"collecting_{len(self.points)}" if self.points else "active"
                return preview_output(self.name, "surface", self.points, closed=len(self.points) >= self.min_points, message=f"已撤销面边界点 {removed}", metadata={"contract": "viewport_creation_affordance_v1", "right_click_completion_menu": True, "point_count": len(self.points), "can_finish": len(self.points) >= self.min_points})
            return message_output(self.name, "No surface point to remove")
        return None

    def cancel(self, context: ToolContext) -> None:
        self.points.clear()
        self.mode = "cancelled"


@dataclass
class BoxBlockTool(ModelingTool):
    name: str = "block_box"
    first_corner: tuple[float, float, float] | None = None
    default_width_y: float = 1.0
    role: str = "structure"

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        xyz, constraint = _constrained_world(event, context, None)
        if self.first_corner is None:
            self.first_corner = xyz
            self.mode = "awaiting_opposite_corner"
            return preview_output(self.name, "box", [xyz], message="已设置体第一角点；移动鼠标预览，左键确定对角点", metadata=_interaction_metadata(event, phase="start", extra={"tool_hint": "pick_box_opposite_corner"}))
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        xyz, constraint = _constrained_world(event, context, self.first_corner)
        x1, y1, z1 = self.first_corner
        x2, y2, z2 = xyz
        ymin = min(y1, y2)
        ymax = max(y1, y2)
        if abs(ymax - ymin) < 1.0e-9:
            ymin -= self.default_width_y * 0.5
            ymax += self.default_width_y * 0.5
        bounds = (min(x1, x2), max(x1, x2), ymin, ymax, min(z1, z2), max(z1, z2))
        result = context.command_stack.execute(CreateBlockCommand(bounds=bounds, role=self.role), context.document)
        entity_id = _created_id_from_result(result)
        _record_constraint_placement(context, self.first_corner, kind="box_corner", entity_id=entity_id)
        lock = _record_constraint_placement(context, xyz, kind="box_corner", entity_id=entity_id)
        self.first_corner = None
        self.mode = "active"
        return _creation_command_output(self.name, result, select_kind="volume", point=xyz, constraint_lock=lock)

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        if self.first_corner is None:
            return None
        xyz, constraint = _constrained_world(event, context, self.first_corner)
        return preview_output(self.name, "box", [self.first_corner, xyz], message="预览体：左键确定对角点；Shift/Ctrl 或锁定沿边/沿法向约束；Esc 取消", metadata=_interaction_metadata(event, extra={"tool_hint": "left_click_finish_box", "constraint_available": ["horizontal", "vertical", "along_edge", "along_normal"]}))

    def on_key_press(self, key: str, context: ToolContext) -> Any:
        if str(key).lower() in {"backspace", "delete"}:
            self.first_corner = None
            self.mode = "active"
            return message_output(self.name, "Box first corner cleared")
        return None

    def cancel(self, context: ToolContext) -> None:
        self.first_corner = None
        self.mode = "cancelled"


__all__ = ["PointTool", "LineTool", "SurfaceTool", "BoxBlockTool"]
