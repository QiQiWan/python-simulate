from __future__ import annotations

"""Interactive 3D viewport tool runtime v2.

The runtime is intentionally Qt-free.  Real UI backends translate mouse/keyboard
signals into ToolEvent objects and consume ViewportToolOutput dictionaries.
"""

from dataclasses import dataclass, field
from typing import Protocol

from geoai_simkit.app.tools.base import ModelingTool, ToolContext, ToolEvent
from geoai_simkit.contracts.viewport import ViewportToolOutput


class RuntimeTool(Protocol):
    name: str
    mode: str

    def on_activate(self, context: ToolContext) -> None: ...
    def on_deactivate(self, context: ToolContext) -> None: ...
    def on_mouse_press(self, event: ToolEvent, context: ToolContext) -> object: ...
    def on_mouse_move(self, event: ToolEvent, context: ToolContext) -> object: ...
    def on_mouse_release(self, event: ToolEvent, context: ToolContext) -> object: ...
    def on_key_press(self, key: str, context: ToolContext) -> object: ...
    def commit(self, context: ToolContext) -> object: ...
    def cancel(self, context: ToolContext) -> None: ...


def _normalize_output(tool: RuntimeTool, value: object) -> ViewportToolOutput:
    if isinstance(value, ViewportToolOutput):
        return value
    if hasattr(value, "to_dict"):
        try:
            return ViewportToolOutput(kind="command", tool=tool.name, command_result=value.to_dict())  # type: ignore[union-attr]
        except Exception:
            pass
    if isinstance(value, dict):
        kind = str(value.get("kind") or "message")
        return ViewportToolOutput(kind=kind if kind in {"none", "preview", "command", "selection", "message", "error"} else "message", tool=tool.name, message=str(value.get("message") or ""), metadata=value)  # type: ignore[arg-type]
    if value is None:
        return ViewportToolOutput(kind="none", tool=tool.name)
    return ViewportToolOutput(kind="message", tool=tool.name, message=str(value))


@dataclass(slots=True)
class ViewportToolRuntime:
    context: ToolContext
    tools: dict[str, RuntimeTool] = field(default_factory=dict)
    active_tool_key: str = ""
    history: list[ViewportToolOutput] = field(default_factory=list)

    def register(self, tool: RuntimeTool) -> None:
        self.tools[tool.name] = tool
        if not self.active_tool_key:
            self.active_tool_key = tool.name

    def activate(self, key: str) -> ViewportToolOutput:
        if key not in self.tools:
            return ViewportToolOutput(kind="error", tool=key, message=f"Unknown tool: {key}")
        if self.active_tool_key and self.active_tool_key in self.tools:
            self.tools[self.active_tool_key].on_deactivate(self.context)
        self.active_tool_key = key
        self.tools[key].on_activate(self.context)
        output = ViewportToolOutput(kind="message", tool=key, message=f"Activated {key}", metadata={"mode": self.tools[key].mode})
        self.history.append(output)
        return output

    def activate_phase_tool(self, tool_payload: object) -> ViewportToolOutput:
        """Activate the runtime tool described by a phase ribbon tool payload."""

        key = "select"
        if isinstance(tool_payload, dict):
            metadata = dict(tool_payload.get("metadata", {}) or {})
            key = str(metadata.get("runtime_tool") or tool_payload.get("runtime_tool") or "select")
        return self.activate(key)

    @property
    def active_tool(self) -> RuntimeTool | None:
        return self.tools.get(self.active_tool_key)

    def mouse_press(self, event: ToolEvent) -> ViewportToolOutput:
        tool = self.active_tool
        if tool is None:
            return ViewportToolOutput(kind="error", tool="", message="No active tool")
        output = _normalize_output(tool, tool.on_mouse_press(event, self.context))
        self.history.append(output)
        return output

    def mouse_move(self, event: ToolEvent) -> ViewportToolOutput:
        tool = self.active_tool
        if tool is None:
            return ViewportToolOutput(kind="error", tool="", message="No active tool")
        output = _normalize_output(tool, tool.on_mouse_move(event, self.context))
        self.history.append(output)
        return output

    def mouse_release(self, event: ToolEvent) -> ViewportToolOutput:
        tool = self.active_tool
        if tool is None:
            return ViewportToolOutput(kind="error", tool="", message="No active tool")
        output = _normalize_output(tool, tool.on_mouse_release(event, self.context))
        self.history.append(output)
        return output

    def key_press(self, key: str) -> ViewportToolOutput:
        tool = self.active_tool
        if tool is None:
            return ViewportToolOutput(kind="error", tool="", message="No active tool")
        if key.lower() in {"escape", "esc"}:
            tool.cancel(self.context)
            output = ViewportToolOutput(kind="message", tool=tool.name, message="Cancelled")
        elif key.lower() in {"enter", "return"}:
            output = _normalize_output(tool, tool.commit(self.context))
        else:
            output = _normalize_output(tool, tool.on_key_press(key, self.context))
        self.history.append(output)
        return output

    def snapshot(self) -> dict[str, object]:
        return {
            "active_tool": self.active_tool_key,
            "registered_tools": sorted(self.tools),
            "history": [item.to_dict() for item in self.history[-20:]],
            "metadata": {"contract": "viewport_tool_runtime_v2"},
        }


def default_geometry_tool_runtime(context: ToolContext) -> ViewportToolRuntime:
    from geoai_simkit.app.tools.geometry_creation_tools import BoxBlockTool, LineTool, PointTool, SurfaceTool
    from geoai_simkit.app.tools.geometry_edit_tools import ApplyCadFeaturesTool, BooleanTool, CopyTool, CutTool, DragMoveTool, ExtrudeTool, MoveTool, RotateTool, ScaleTool
    from geoai_simkit.app.tools.select_tool import SelectTool

    runtime = ViewportToolRuntime(context=context)
    for tool in (
        SelectTool(), PointTool(), LineTool(), SurfaceTool(), BoxBlockTool(),
        DragMoveTool(), DragMoveTool(name="move"), CopyTool(), RotateTool(), ScaleTool(),
        ExtrudeTool(), CutTool(), BooleanTool(operation="union"), BooleanTool(name="boolean_subtract", operation="subtract"), ApplyCadFeaturesTool(),
    ):
        runtime.register(tool)
    runtime.activate("select")
    return runtime


__all__ = ["ViewportToolRuntime", "default_geometry_tool_runtime"]
