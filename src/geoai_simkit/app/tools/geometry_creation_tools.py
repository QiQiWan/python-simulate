from __future__ import annotations

"""Stateful point/line/surface/block creation tools for GUI viewports."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent
from geoai_simkit.commands import CreateBlockCommand, CreateLineCommand, CreatePointCommand, CreateSurfaceCommand


def _world(event: ToolEvent) -> tuple[float, float, float]:
    return tuple(float(v) for v in (event.world or (event.x, 0.0, event.y)))  # type: ignore[return-value]


class PointTool(ModelingTool):
    name = "point"

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        if context.command_stack is None:
            return None
        x, y, z = _world(event)
        return context.command_stack.execute(CreatePointCommand(x=x, y=y, z=z), context.document)


@dataclass
class LineTool(ModelingTool):
    name: str = "line"
    pending_start: tuple[float, float, float] | None = None

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        xyz = _world(event)
        if self.pending_start is None:
            self.pending_start = xyz
            self.mode = "awaiting_end"
            return {"tool": self.name, "mode": self.mode, "start": list(xyz)}
        if context.command_stack is None:
            return None
        result = context.command_stack.execute(CreateLineCommand(start=self.pending_start, end=xyz), context.document)
        self.pending_start = None
        self.mode = "active"
        return result

    def cancel(self, context: ToolContext) -> None:
        self.pending_start = None
        self.mode = "cancelled"


@dataclass
class SurfaceTool(ModelingTool):
    name: str = "surface"
    points: list[tuple[float, float, float]] = field(default_factory=list)
    min_points: int = 3

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        xyz = _world(event)
        self.points.append(xyz)
        self.mode = f"collecting_{len(self.points)}"
        return {"tool": self.name, "mode": self.mode, "points": [list(p) for p in self.points]}

    def commit(self, context: ToolContext) -> Any:
        if len(self.points) < self.min_points or context.command_stack is None:
            return None
        result = context.command_stack.execute(CreateSurfaceCommand(coords=tuple(self.points)), context.document)
        self.points.clear()
        self.mode = "active"
        return result

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
        xyz = _world(event)
        if self.first_corner is None:
            self.first_corner = xyz
            self.mode = "awaiting_opposite_corner"
            return {"tool": self.name, "mode": self.mode, "first_corner": list(xyz)}
        if context.command_stack is None:
            return None
        x1, y1, z1 = self.first_corner
        x2, y2, z2 = xyz
        ymin = min(y1, y2)
        ymax = max(y1, y2)
        if abs(ymax - ymin) < 1.0e-9:
            ymin -= self.default_width_y * 0.5
            ymax += self.default_width_y * 0.5
        bounds = (min(x1, x2), max(x1, x2), ymin, ymax, min(z1, z2), max(z1, z2))
        result = context.command_stack.execute(CreateBlockCommand(bounds=bounds, role=self.role), context.document)
        self.first_corner = None
        self.mode = "active"
        return result

    def cancel(self, context: ToolContext) -> None:
        self.first_corner = None
        self.mode = "cancelled"


__all__ = ["PointTool", "LineTool", "SurfaceTool", "BoxBlockTool"]
