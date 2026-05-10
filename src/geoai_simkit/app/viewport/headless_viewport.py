from __future__ import annotations

"""Headless viewport implementation used by tests and non-3D fallback UI."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.document.selection import SelectionRef


@dataclass(slots=True)
class HeadlessViewport:
    state: ViewportState = field(default_factory=ViewportState)
    event_log: list[dict[str, Any]] = field(default_factory=list)

    def load_document(self, document: Any, *, stage_id: str | None = None) -> ViewportState:
        self.state.update_from_engineering_document(document, stage_id=stage_id)
        self.event_log.append({"event": "load_document", "stage_id": self.state.active_stage_id, "primitive_count": len(self.state.primitives)})
        return self.state

    def select_entity(self, entity_id: str, entity_type: str = "block") -> SelectionRef | None:
        ref = self.state.pick_by_entity_id(entity_id, entity_type=entity_type)
        self.event_log.append({"event": "select_entity", "entity_id": entity_id, "entity_type": entity_type, "selected": ref is not None})
        return ref

    def render_payload(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload["event_log"] = list(self.event_log[-20:])
        return payload
