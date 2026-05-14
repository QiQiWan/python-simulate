from __future__ import annotations

"""Interactive edit/transform tools for direct 3D geometry modeling."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent
from geoai_simkit.app.viewport.preview_overlay import message_output, preview_output
from geoai_simkit.contracts.viewport import ViewportToolOutput
from geoai_simkit.commands.cad_kernel_commands import ExecuteCadFeaturesCommand
from geoai_simkit.commands.interactive_geometry_commands import (
    BooleanGeometryCommand,
    CopyGeometryCommand,
    CutVolumeCommand,
    ExtrudeSurfaceCommand,
    TransformGeometryCommand,
)


def _world(event: ToolEvent) -> tuple[float, float, float]:
    return tuple(float(v) for v in (event.world or (event.x, 0.0, event.y)))  # type: ignore[return-value]


def _selected_ids(context: ToolContext, fallback: str | None = None) -> tuple[str, ...]:
    controller = context.metadata.get("selection_controller") if isinstance(context.metadata, dict) else None
    ids: list[str] = []
    if controller is not None and hasattr(controller, "selected_ids"):
        try:
            ids = list(controller.selected_ids())
        except Exception:
            ids = []
    if not ids and fallback:
        ids = [fallback]
    return tuple(str(v) for v in ids if v)


def _primitive_for_entity(context: ToolContext, entity_id: str):
    viewport = getattr(context, "viewport", None)
    primitives = getattr(viewport, "primitives", {}) or {}
    for primitive in primitives.values():
        if getattr(primitive, "entity_id", "") == entity_id:
            return primitive
    return None


def _bounds_for_entity(context: ToolContext, entity_id: str):
    primitive = _primitive_for_entity(context, entity_id)
    bounds = getattr(primitive, "bounds", None) if primitive is not None else None
    if bounds is None:
        return None
    return tuple(float(v) for v in bounds)


def _box_preview_points(bounds: tuple[float, float, float, float, float, float]) -> list[tuple[float, float, float]]:
    return [(bounds[0], bounds[2], bounds[4]), (bounds[1], bounds[3], bounds[5])]


def _cut_plane_points(bounds: tuple[float, float, float, float, float, float], axis: str, coordinate: float) -> list[tuple[float, float, float]]:
    x0, x1, y0, y1, z0, z1 = bounds
    c = float(coordinate)
    if axis == "x":
        return [(c, y0, z0), (c, y1, z0), (c, y1, z1), (c, y0, z1)]
    if axis == "y":
        return [(x0, c, z0), (x1, c, z0), (x1, c, z1), (x0, c, z1)]
    return [(x0, y0, c), (x1, y0, c), (x1, y1, c), (x0, y1, c)]


def _axis_constrained_delta(delta: tuple[float, float, float], axis: str) -> tuple[float, float, float]:
    axis = axis.lower().strip()
    if axis == "x":
        return (delta[0], 0.0, 0.0)
    if axis == "y":
        return (0.0, delta[1], 0.0)
    if axis == "z":
        return (0.0, 0.0, delta[2])
    return delta


@dataclass
class DragMoveTool(ModelingTool):
    name: str = "drag_move"
    start_world: tuple[float, float, float] | None = None
    entity_ids: tuple[str, ...] = ()
    entity_type: str = ""
    handle_axis: str = ""

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        self.start_world = _world(event)
        self.entity_ids = _selected_ids(context, event.picked_entity_id)
        self.entity_type = str(event.metadata.get("picked_kind") or "")
        self.handle_axis = str(event.metadata.get("handle_axis") or "")
        if not self.entity_ids:
            return message_output(self.name, "Select or pick an entity before dragging", error=True)
        self.mode = "dragging"
        suffix = f" along {self.handle_axis.upper()}" if self.handle_axis else ""
        return preview_output(self.name, "line", [self.start_world], message=f"Drag to move {', '.join(self.entity_ids)}{suffix}")

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        if self.start_world is None or not self.entity_ids:
            return None
        end = _world(event)
        return preview_output(self.name, "line", [self.start_world, end], message="Move preview")

    def on_mouse_release(self, event: ToolEvent, context: ToolContext) -> Any:
        if self.start_world is None or not self.entity_ids:
            return None
        end = _world(event)
        delta = (end[0] - self.start_world[0], end[1] - self.start_world[1], end[2] - self.start_world[2])
        dx, dy, dz = _axis_constrained_delta(delta, self.handle_axis)
        self.start_world = None
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(TransformGeometryCommand(entity_ids=self.entity_ids, entity_type=self.entity_type, translate=(dx, dy, dz)), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())

    def cancel(self, context: ToolContext) -> None:
        self.start_world = None
        self.entity_ids = ()
        self.handle_axis = ""
        self.mode = "cancelled"


class MoveTool(DragMoveTool):
    name = "move"


@dataclass
class CopyTool(DragMoveTool):
    name: str = "copy"

    def on_mouse_release(self, event: ToolEvent, context: ToolContext) -> Any:
        if self.start_world is None or not self.entity_ids:
            return None
        end = _world(event)
        offset = _axis_constrained_delta((end[0] - self.start_world[0], end[1] - self.start_world[1], end[2] - self.start_world[2]), self.handle_axis)
        self.start_world = None
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(CopyGeometryCommand(entity_ids=self.entity_ids, entity_type=self.entity_type, offset=offset), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class RotateTool(ModelingTool):
    name: str = "rotate"
    angle_deg: float = 15.0

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        entity_ids = _selected_ids(context, event.picked_entity_id)
        if not entity_ids:
            return message_output(self.name, "Select or pick an entity to rotate", error=True)
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(TransformGeometryCommand(entity_ids=entity_ids, entity_type=str(event.metadata.get("picked_kind") or ""), rotate_z_deg=self.angle_deg), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class ScaleTool(ModelingTool):
    name: str = "scale"
    factor: float = 1.1

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        entity_ids = _selected_ids(context, event.picked_entity_id)
        if not entity_ids:
            return message_output(self.name, "Select or pick an entity to scale", error=True)
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(TransformGeometryCommand(entity_ids=entity_ids, entity_type=str(event.metadata.get("picked_kind") or ""), scale=(self.factor, self.factor, self.factor)), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class ExtrudeTool(ModelingTool):
    name: str = "extrude"
    vector: tuple[float, float, float] = (0.0, 0.0, -5.0)

    def _target_surface(self, event: ToolEvent, context: ToolContext) -> str:
        kind = str(event.metadata.get("picked_kind") or "")
        if kind in {"face", "surface"}:
            return event.picked_entity_id or ""
        return event.picked_entity_id or (next(iter(_selected_ids(context)), ""))

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        surface_id = self._target_surface(event, context)
        bounds = _bounds_for_entity(context, surface_id) if surface_id else None
        if bounds is None:
            return None
        dx, dy, dz = [float(v) for v in self.vector]
        moved = (bounds[0] + min(0.0, dx), bounds[1] + max(0.0, dx), bounds[2] + min(0.0, dy), bounds[3] + max(0.0, dy), bounds[4] + min(0.0, dz), bounds[5] + max(0.0, dz))
        return preview_output(self.name, "box", _box_preview_points(moved), message=f"Extrude preview: {surface_id}")

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        surface_id = self._target_surface(event, context)
        if not surface_id:
            return message_output(self.name, "Pick/select a surface or face to extrude", error=True)
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(ExtrudeSurfaceCommand(surface_id=surface_id, vector=self.vector), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class CutTool(ModelingTool):
    name: str = "cut"
    axis: str = "z"

    def _target_volume(self, event: ToolEvent, context: ToolContext) -> str:
        source = str(event.metadata.get("source_entity_id") or "")
        if source:
            return source
        return event.picked_entity_id or (next(iter(_selected_ids(context)), ""))

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        volume_id = self._target_volume(event, context)
        bounds = _bounds_for_entity(context, volume_id) if volume_id else None
        if bounds is None:
            return None
        coord = _world(event)[2 if self.axis == "z" else (1 if self.axis == "y" else 0)]
        lo_hi = {"x": (bounds[0], bounds[1]), "y": (bounds[2], bounds[3]), "z": (bounds[4], bounds[5])}[self.axis]
        coord = max(min(float(coord), lo_hi[1]), lo_hi[0])
        return preview_output(self.name, "cut_plane", _cut_plane_points(bounds, self.axis, coord), message=f"Cut preview: {volume_id} {self.axis}={coord:.3f}")

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        volume_id = self._target_volume(event, context)
        if not volume_id:
            return message_output(self.name, "Pick/select a volume to cut", error=True)
        coord = _world(event)[2 if self.axis == "z" else (1 if self.axis == "y" else 0)]
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(CutVolumeCommand(volume_id=volume_id, axis=self.axis, coordinate=coord), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class BooleanTool(ModelingTool):
    name: str = "boolean"
    operation: str = "union"

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        entity_ids = _selected_ids(context, event.picked_entity_id)
        bounds_rows = [b for eid in entity_ids if (b := _bounds_for_entity(context, eid)) is not None]
        if not bounds_rows:
            return None
        xs0, xs1 = [b[0] for b in bounds_rows], [b[1] for b in bounds_rows]
        ys0, ys1 = [b[2] for b in bounds_rows], [b[3] for b in bounds_rows]
        zs0, zs1 = [b[4] for b in bounds_rows], [b[5] for b in bounds_rows]
        bounds = (min(xs0), max(xs1), min(ys0), max(ys1), min(zs0), max(zs1))
        return preview_output(self.name, "box", _box_preview_points(bounds), message=f"Boolean {self.operation} preview: {len(entity_ids)} volume(s)")

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        entity_ids = _selected_ids(context, event.picked_entity_id)
        if len(entity_ids) < 1:
            return message_output(self.name, "Select one or more volumes before boolean operation", error=True)
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(BooleanGeometryCommand(operation=self.operation, target_ids=entity_ids), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


@dataclass
class ApplyCadFeaturesTool(ModelingTool):
    name: str = "apply_cad_features"

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(ExecuteCadFeaturesCommand(require_native=False, allow_fallback=True), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())

    def commit(self, context: ToolContext) -> Any:
        if context.command_stack is None:
            return message_output(self.name, "No command stack", error=True)
        result = context.command_stack.execute(ExecuteCadFeaturesCommand(require_native=False, allow_fallback=True), context.document)
        return ViewportToolOutput(kind="command", tool=self.name, message=result.message, command_result=result.to_dict())


__all__ = [
    "DragMoveTool",
    "MoveTool",
    "CopyTool",
    "RotateTool",
    "ScaleTool",
    "ExtrudeTool",
    "CutTool",
    "BooleanTool",
    "ApplyCadFeaturesTool",
]
