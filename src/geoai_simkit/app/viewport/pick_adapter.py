from __future__ import annotations

"""Qt/PyVista-independent pick conversion helpers."""

from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.contracts.viewport import ViewportPickResult


def _with_topology_identity_metadata(metadata: dict[str, object]) -> dict[str, object]:
    data = dict(metadata or {})
    topology_id = str(data.get("topology_id") or data.get("id") or "")
    shape_id = str(data.get("shape_id") or "")
    kind = str(data.get("topology_kind") or data.get("kind") or "")
    if topology_id and shape_id and kind in {"solid", "face", "edge"}:
        key = f"topology:{kind}:{shape_id}:{topology_id}"
        data.setdefault("topology_identity_key", key)
        data.setdefault("selection_key", key)
        data.setdefault("entity_id", topology_id)
        data.setdefault("picked_kind", kind)
    return data


def pick_from_tool_event(event: object) -> ViewportPickResult:
    world = tuple(float(v) for v in (getattr(event, "world", None) or (getattr(event, "x", 0.0), 0.0, getattr(event, "y", 0.0))))
    metadata = _with_topology_identity_metadata(dict(getattr(event, "metadata", {}) or {}))
    kind = str(metadata.get("picked_kind") or metadata.get("topology_kind") or metadata.get("entity_type") or "empty")
    entity_id = str(getattr(event, "picked_entity_id", None) or metadata.get("topology_id") or metadata.get("entity_id") or "")
    primitive_id = str(metadata.get("primitive_id") or "")
    if entity_id and kind == "empty":
        kind = "block"
    return ViewportPickResult(kind=kind, entity_id=entity_id, primitive_id=primitive_id, world=world, metadata=metadata)  # type: ignore[arg-type]


def pick_by_entity_id(state: ViewportState, entity_id: str, *, entity_kind: str = "block") -> ViewportPickResult:
    for primitive in state.primitives.values():
        if primitive.entity_id == entity_id and primitive.kind == entity_kind:
            bounds = primitive.bounds
            if bounds is None:
                world = (0.0, 0.0, 0.0)
            else:
                world = ((bounds[0] + bounds[1]) * 0.5, (bounds[2] + bounds[3]) * 0.5, (bounds[4] + bounds[5]) * 0.5)
            return ViewportPickResult(kind=entity_kind, entity_id=entity_id, primitive_id=primitive.id, world=world, metadata=_with_topology_identity_metadata(dict(primitive.metadata)))  # type: ignore[arg-type]
    return ViewportPickResult(kind="empty", world=(0.0, 0.0, 0.0))


__all__ = ["pick_by_entity_id", "pick_from_tool_event"]
