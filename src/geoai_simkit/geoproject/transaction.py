from __future__ import annotations

"""Transaction, dirty-state and invalidation helpers for GeoProjectDocument.

The classes in this module are intentionally dependency-light.  They provide a
single place where GUI commands can record which parts of the project changed,
which downstream models became stale, and which entities were touched.  The
actual GUI and solver can then read the metadata from GeoProjectDocument without
needing to know which command produced the change.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
import copy


_SCOPE_TO_DIRTY_FLAGS: dict[str, tuple[str, ...]] = {
    "project": ("project_dirty",),
    "soil": ("soil_dirty", "mesh_dirty", "solver_dirty", "result_stale"),
    "geometry": ("geometry_dirty", "topology_dirty", "mesh_dirty", "solver_dirty", "result_stale"),
    "topology": ("topology_dirty", "mesh_dirty", "solver_dirty", "result_stale"),
    "structure": ("structure_dirty", "topology_dirty", "mesh_dirty", "solver_dirty", "result_stale"),
    "material": ("material_dirty", "solver_dirty", "result_stale"),
    "mesh": ("mesh_dirty", "solver_dirty", "result_stale"),
    "phase": ("phase_dirty", "solver_dirty", "result_stale"),
    "boundary": ("boundary_dirty", "solver_dirty", "result_stale"),
    "load": ("load_dirty", "solver_dirty", "result_stale"),
    "water": ("water_dirty", "solver_dirty", "result_stale"),
    "solver": ("solver_dirty", "result_stale"),
    "result": ("result_stale",),
}

_SCOPE_TO_INVALIDATED_COMPONENTS: dict[str, tuple[str, ...]] = {
    "project": ("object_tree", "property_panel"),
    "soil": ("topology_graph", "mesh_document", "compiled_phase_models", "result_store"),
    "geometry": ("topology_graph", "mesh_document", "mesh_entity_map", "compiled_phase_models", "result_store"),
    "topology": ("mesh_document", "mesh_entity_map", "compiled_phase_models", "result_store"),
    "structure": ("topology_graph", "mesh_document", "compiled_phase_models", "result_store"),
    "material": ("compiled_phase_models", "result_store"),
    "mesh": ("compiled_phase_models", "result_store"),
    "phase": ("phase_state_snapshots", "compiled_phase_models", "result_store"),
    "boundary": ("compiled_phase_models", "result_store"),
    "load": ("compiled_phase_models", "result_store"),
    "water": ("phase_state_snapshots", "compiled_phase_models", "result_store"),
    "solver": ("compiled_phase_models", "result_store"),
    "result": ("result_store",),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DirtyGraph:
    """Dirty flags propagated from high-level engineering edit scopes."""

    flags: dict[str, bool] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    last_scopes: list[str] = field(default_factory=list)

    def mark(self, scopes: Iterable[str], *, message: str = "") -> None:
        seen: list[str] = []
        for raw_scope in scopes:
            scope = str(raw_scope).lower().strip()
            if not scope:
                continue
            if scope not in seen:
                seen.append(scope)
            for flag in _SCOPE_TO_DIRTY_FLAGS.get(scope, (f"{scope}_dirty", "result_stale")):
                self.flags[str(flag)] = True
        self.last_scopes = seen
        if message:
            self.messages.append(message)
            self.messages[:] = self.messages[-100:]

    def clear(self, *flag_names: str) -> None:
        if not flag_names:
            for key in list(self.flags):
                self.flags[key] = False
            return
        for key in flag_names:
            self.flags[str(key)] = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "flags": dict(self.flags),
            "messages": list(self.messages),
            "last_scopes": list(self.last_scopes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DirtyGraph":
        data = dict(data or {})
        return cls(
            flags={str(k): bool(v) for k, v in dict(data.get("flags", {}) or {}).items()},
            messages=[str(v) for v in list(data.get("messages", []) or [])],
            last_scopes=[str(v) for v in list(data.get("last_scopes", []) or [])],
        )


@dataclass(slots=True)
class InvalidationGraph:
    """Tracks downstream components invalidated by engineering edits."""

    invalidated: dict[str, bool] = field(default_factory=dict)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    version: int = 0

    def invalidate(self, scopes: Iterable[str], *, reason: str = "") -> None:
        touched = False
        for raw_scope in scopes:
            scope = str(raw_scope).lower().strip()
            for component in _SCOPE_TO_INVALIDATED_COMPONENTS.get(scope, (scope,)):
                self.invalidated[component] = True
                if reason:
                    self.reasons.setdefault(component, []).append(reason)
                    self.reasons[component] = self.reasons[component][-20:]
                touched = True
        if touched:
            self.version += 1

    def mark_clean(self, *component_names: str) -> None:
        for component in component_names:
            self.invalidated[str(component)] = False

    def is_invalidated(self, component_name: str) -> bool:
        return bool(self.invalidated.get(str(component_name), False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "invalidated": dict(self.invalidated),
            "reasons": {k: list(v) for k, v in self.reasons.items()},
            "version": int(self.version),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "InvalidationGraph":
        data = dict(data or {})
        return cls(
            invalidated={str(k): bool(v) for k, v in dict(data.get("invalidated", {}) or {}).items()},
            reasons={str(k): [str(v) for v in list(vals or [])] for k, vals in dict(data.get("reasons", {}) or {}).items()},
            version=int(data.get("version", 0)),
        )


@dataclass(slots=True)
class GeoProjectTransaction:
    """Small transaction wrapper used by undoable GeoProjectDocument commands."""

    document: Any
    action: str
    scopes: list[str] = field(default_factory=list)
    affected_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def begin(self) -> "GeoProjectTransaction":
        self._backup = copy.deepcopy(self.document.to_dict()) if hasattr(self.document, "to_dict") else None
        return self

    def mark(self, *scopes: str, affected_entities: Iterable[str] = (), **metadata: Any) -> None:
        for scope in scopes:
            scope = str(scope)
            if scope and scope not in self.scopes:
                self.scopes.append(scope)
        for entity_id in affected_entities:
            sid = str(entity_id)
            if sid and sid not in self.affected_entities:
                self.affected_entities.append(sid)
        self.metadata.update(metadata)

    def commit(self, *, message: str = "") -> dict[str, Any]:
        mark_geoproject_changed(
            self.document,
            self.scopes or ["project"],
            action=self.action,
            affected_entities=self.affected_entities,
            message=message or self.action,
            metadata=self.metadata,
        )
        return self.to_dict()

    def rollback(self) -> bool:
        if self._backup is None or not hasattr(self.document, "from_dict"):
            return False
        restored = self.document.from_dict(self._backup)
        for field_name in getattr(self.document, "__dataclass_fields__", {}):
            setattr(self.document, field_name, getattr(restored, field_name))
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "scopes": list(self.scopes),
            "affected_entities": list(self.affected_entities),
            "metadata": dict(self.metadata),
        }


def get_dirty_graph(document: Any) -> DirtyGraph:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, dict):
        return DirtyGraph()
    graph = metadata.get("DirtyGraph")
    if isinstance(graph, DirtyGraph):
        return graph
    graph = DirtyGraph.from_dict(graph if isinstance(graph, dict) else None)
    metadata["DirtyGraph"] = graph
    return graph


def get_invalidation_graph(document: Any) -> InvalidationGraph:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, dict):
        return InvalidationGraph()
    graph = metadata.get("InvalidationGraph")
    if isinstance(graph, InvalidationGraph):
        return graph
    graph = InvalidationGraph.from_dict(graph if isinstance(graph, dict) else None)
    metadata["InvalidationGraph"] = graph
    return graph


def mark_geoproject_changed(
    document: Any,
    scopes: Iterable[str],
    *,
    action: str = "edit",
    affected_entities: Iterable[str] = (),
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Mark GeoProjectDocument scopes dirty and record invalidation metadata."""

    scopes = [str(scope).lower().strip() for scope in scopes if str(scope).strip()]
    if not scopes:
        scopes = ["project"]
    dirty = get_dirty_graph(document)
    invalidation = get_invalidation_graph(document)
    reason = message or action
    dirty.mark(scopes, message=reason)
    invalidation.invalidate(scopes, reason=reason)
    doc_metadata = getattr(document, "metadata", None)
    if isinstance(doc_metadata, dict):
        doc_metadata["dirty"] = True
        doc_metadata["DirtyGraph"] = dirty.to_dict()
        doc_metadata["InvalidationGraph"] = invalidation.to_dict()
        log = list(doc_metadata.get("transaction_log", []) or [])
        log.append({
            "time": _utc_now(),
            "action": action,
            "scopes": scopes,
            "affected_entities": [str(v) for v in affected_entities],
            "message": reason,
            "metadata": dict(metadata or {}),
        })
        doc_metadata["transaction_log"] = log[-200:]


__all__ = [
    "DirtyGraph",
    "InvalidationGraph",
    "GeoProjectTransaction",
    "get_dirty_graph",
    "get_invalidation_graph",
    "mark_geoproject_changed",
]
