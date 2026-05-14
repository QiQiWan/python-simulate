from __future__ import annotations

"""Selection controller for multi-select, box-select and inverse selection.

This module is Qt-free so selection behaviour can be regression-tested without
running a desktop event loop.
"""

from dataclasses import dataclass, field
from typing import Iterable, Any

from geoai_simkit.app.viewport.viewport_state import ViewportState, ScenePrimitive
from geoai_simkit.contracts.viewport import ViewportSelectionItem, ViewportSelectionSet


def _bounds_intersect(a: tuple[float, float, float, float, float, float], b: tuple[float, float, float, float, float, float]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2] or a[5] < b[4] or b[5] < a[4])


def _selection_key(entity_id: str, kind: str, metadata: dict[str, Any] | None = None) -> str:
    data = dict(metadata or {})
    return str(
        data.get("topology_identity_key")
        or data.get("selection_key")
        or data.get("topology_id")
        or f"viewport:{kind}:{entity_id}"
    )


@dataclass(slots=True)
class SelectionController:
    selected: dict[str, ViewportSelectionItem] = field(default_factory=dict)

    def clear(self) -> ViewportSelectionSet:
        self.selected.clear()
        return self.to_selection_set(mode="clear")

    def select(self, entity_id: str, kind: str = "block", *, mode: str = "replace", metadata: dict[str, Any] | None = None) -> ViewportSelectionSet:
        data = dict(metadata or {})
        key = _selection_key(entity_id, kind, data)
        data.setdefault("selection_key", key)
        item = ViewportSelectionItem(kind=kind, entity_id=entity_id, display_name=entity_id, metadata=data)  # type: ignore[arg-type]
        normalized = mode.lower()
        if normalized in {"add", "shift"}:
            self.selected[key] = item
        elif normalized in {"toggle", "ctrl", "control"}:
            if key in self.selected:
                self.selected.pop(key, None)
            else:
                self.selected[key] = item
        else:
            self.selected.clear()
            if entity_id:
                self.selected[key] = item
        return self.to_selection_set(mode=normalized)

    def box_select(self, state: ViewportState, bounds: tuple[float, float, float, float, float, float], *, mode: str = "replace", kinds: Iterable[str] | None = None) -> ViewportSelectionSet:
        if mode == "replace":
            self.selected.clear()
        allowed = None if kinds is None else {str(k) for k in kinds}
        for primitive in state.primitives.values():
            if not primitive.pickable or primitive.bounds is None:
                continue
            if allowed is not None and primitive.kind not in allowed:
                continue
            if _bounds_intersect(bounds, primitive.bounds):
                self.select(primitive.entity_id, primitive.kind, mode="add", metadata={"primitive_id": primitive.id})
        return self.to_selection_set(mode="box")

    def invert(self, state: ViewportState, *, kinds: Iterable[str] | None = None) -> ViewportSelectionSet:
        allowed = None if kinds is None else {str(k) for k in kinds}
        next_selected: dict[str, ViewportSelectionItem] = {}
        for primitive in state.primitives.values():
            if not primitive.pickable:
                continue
            if allowed is not None and primitive.kind not in allowed:
                continue
            metadata = {**dict(primitive.metadata), "primitive_id": primitive.id}
            key = _selection_key(primitive.entity_id, primitive.kind, metadata)
            if key not in self.selected:
                metadata.setdefault("selection_key", key)
                next_selected[key] = ViewportSelectionItem(primitive.kind, primitive.entity_id, primitive.entity_id, metadata)  # type: ignore[arg-type]
        self.selected = next_selected
        return self.to_selection_set(mode="invert")

    def to_selection_set(self, *, mode: str = "replace") -> ViewportSelectionSet:
        return ViewportSelectionSet(tuple(self.selected.values()), mode=mode, metadata={"contract": "viewport_selection_controller_v1", "selected_count": len(self.selected)})

    def current_selection(self) -> ViewportSelectionSet:
        return self.to_selection_set(mode="current")

    def selected_ids(self) -> list[str]:
        return [item.entity_id for item in self.selected.values()]

    def selected_keys(self) -> list[str]:
        return list(self.selected)

    def to_dict(self) -> dict[str, Any]:
        return {"contract": "viewport_selection_controller_v1", "selected_ids": self.selected_ids(), "selected_keys": self.selected_keys(), "selected_count": len(self.selected)}


__all__ = ["SelectionController"]
