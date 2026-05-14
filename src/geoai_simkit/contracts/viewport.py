from __future__ import annotations

"""Viewport picking and interaction contracts for Qt/PyVista-independent tools."""

from dataclasses import dataclass, field
from typing import Literal, Mapping

JsonMap = Mapping[str, object]
ViewportEntityKind = Literal[
    "point",
    "line",
    "edge",
    "surface",
    "face",
    "volume",
    "block",
    "mesh_node",
    "mesh_edge",
    "mesh_face",
    "mesh_cell",
    "boundary_face",
    "interface_pair",
    "result_node",
    "result_cell",
    "empty",
]
ToolOutputKind = Literal["none", "preview", "command", "selection", "message", "error"]


@dataclass(frozen=True, slots=True)
class ViewportPickResult:
    kind: ViewportEntityKind = "empty"
    entity_id: str = ""
    primitive_id: str = ""
    world: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] | None = None
    distance: float = 0.0
    metadata: JsonMap = field(default_factory=dict)

    @property
    def hit(self) -> bool:
        return self.kind != "empty" or bool(self.entity_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "primitive_id": self.primitive_id,
            "world": list(self.world),
            "normal": None if self.normal is None else list(self.normal),
            "distance": float(self.distance),
            "hit": self.hit,
            "metadata": {"contract": "viewport_pick_result_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class ViewportSelectionItem:
    kind: ViewportEntityKind
    entity_id: str
    display_name: str = ""
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "display_name": self.display_name or self.entity_id,
            "metadata": {"contract": "viewport_selection_item_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class ViewportSelectionSet:
    items: tuple[ViewportSelectionItem, ...] = ()
    mode: str = "replace"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "mode": self.mode,
            "metadata": {"contract": "viewport_selection_set_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class ViewportPreviewGeometry:
    kind: str
    points: tuple[tuple[float, float, float], ...] = ()
    closed: bool = False
    style: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "points": [list(point) for point in self.points],
            "closed": bool(self.closed),
            "style": dict(self.style),
            "metadata": {"contract": "viewport_preview_geometry_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class ViewportToolOutput:
    kind: ToolOutputKind = "none"
    tool: str = ""
    message: str = ""
    preview: ViewportPreviewGeometry | None = None
    selection: ViewportSelectionSet | None = None
    command_result: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "tool": self.tool,
            "message": self.message,
            "preview": None if self.preview is None else self.preview.to_dict(),
            "selection": None if self.selection is None else self.selection.to_dict(),
            "command_result": dict(self.command_result),
            "metadata": {"contract": "viewport_tool_output_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class WorkPlane:
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    x_axis: tuple[float, float, float] = (1.0, 0.0, 0.0)
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "origin": list(self.origin),
            "normal": list(self.normal),
            "x_axis": list(self.x_axis),
            "metadata": {"contract": "work_plane_v1", **dict(self.metadata)},
        }


__all__ = [
    "JsonMap",
    "ToolOutputKind",
    "ViewportEntityKind",
    "ViewportPickResult",
    "ViewportPreviewGeometry",
    "ViewportSelectionItem",
    "ViewportSelectionSet",
    "ViewportToolOutput",
    "WorkPlane",
]
