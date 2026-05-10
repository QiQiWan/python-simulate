from __future__ import annotations

"""Tool state machine interface for viewport mouse/keyboard interaction."""

from dataclasses import dataclass, field
from typing import Any, Literal

MouseButton = Literal["left", "middle", "right", "none"]


@dataclass(slots=True)
class ToolEvent:
    x: float = 0.0
    y: float = 0.0
    world: tuple[float, float, float] | None = None
    button: MouseButton = "none"
    modifiers: tuple[str, ...] = ()
    picked_entity_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolContext:
    document: Any
    viewport: Any
    command_stack: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelingTool:
    name: str = "tool"
    mode: str = "idle"

    def on_activate(self, context: ToolContext) -> None:
        self.mode = "active"

    def on_deactivate(self, context: ToolContext) -> None:
        self.mode = "idle"

    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> Any:
        return None

    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> Any:
        return None

    def on_mouse_release(self, event: ToolEvent, context: ToolContext) -> Any:
        return None

    def on_key_press(self, key: str, context: ToolContext) -> Any:
        return None

    def preview(self, context: ToolContext) -> dict[str, Any]:
        return {"tool": self.name, "mode": self.mode}

    def commit(self, context: ToolContext) -> Any:
        return None

    def cancel(self, context: ToolContext) -> None:
        self.mode = "cancelled"
