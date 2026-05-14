from __future__ import annotations

"""Canonical topology identity records shared by CAD, viewport and GUI panels.

The records in this module are deliberately small and dependency-free.  They are
used as a stable hand-off format between the native CAD/OCC/IFC layer, the
headless services, the viewport picking adapter and GUI panels.  A selected
face or edge should be representable as a :class:`TopologyElementIdentity`
without importing Qt, PyVista, OCC or IfcOpenShell.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

TopologyKind = Literal["solid", "face", "edge", "vertex", "mesh_cell", "entity", "unknown"]
IdentityConfidence = Literal["native", "certified", "derived", "heuristic", "unknown"]
LineageKind = Literal["unchanged", "preserved", "modified", "generated", "deleted", "split", "merge", "native_history", "derived"]

TOPOLOGY_IDENTITY_CONTRACT = "geoai_simkit_topology_identity_v1"


def _ls(value: Any) -> list[str]:
    return [str(item) for item in list(value or []) if str(item)]


def _meta(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True, slots=True)
class ModelEntityIdentity:
    """Stable engineering entity identity, e.g. a GeoProject volume or IFC product."""

    id: str
    entity_type: str = "volume"
    source: str = "geoproject"
    display_name: str = ""
    material_id: str = ""
    phase_ids: list[str] = field(default_factory=list)
    role: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"entity:{self.source}:{self.entity_type}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": TOPOLOGY_IDENTITY_CONTRACT,
            "key": self.key,
            "id": self.id,
            "entity_type": self.entity_type,
            "source": self.source,
            "display_name": self.display_name or self.id,
            "material_id": self.material_id,
            "phase_ids": list(self.phase_ids),
            "role": self.role,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ModelEntityIdentity":
        d = dict(data or {})
        return cls(
            id=str(d.get("id") or d.get("entity_id") or ""),
            entity_type=str(d.get("entity_type") or "volume"),
            source=str(d.get("source") or "geoproject"),
            display_name=str(d.get("display_name") or d.get("name") or ""),
            material_id=str(d.get("material_id") or ""),
            phase_ids=_ls(d.get("phase_ids")),
            role=str(d.get("role") or ""),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class ShapeNodeIdentity:
    """CAD shape identity linked to one or more engineering entities."""

    id: str
    kind: str = "solid"
    backend: str = "cad_facade"
    source_entity_ids: list[str] = field(default_factory=list)
    native_shape_available: bool = False
    brep_serialized: bool = False
    confidence: IdentityConfidence = "derived"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"shape:{self.backend}:{self.kind}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": TOPOLOGY_IDENTITY_CONTRACT,
            "key": self.key,
            "id": self.id,
            "kind": self.kind,
            "backend": self.backend,
            "source_entity_ids": list(self.source_entity_ids),
            "native_shape_available": bool(self.native_shape_available),
            "brep_serialized": bool(self.brep_serialized),
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ShapeNodeIdentity":
        d = dict(data or {})
        return cls(
            id=str(d.get("id") or d.get("shape_id") or ""),
            kind=str(d.get("kind") or "solid"),
            backend=str(d.get("backend") or "cad_facade"),
            source_entity_ids=_ls(d.get("source_entity_ids")),
            native_shape_available=bool(d.get("native_shape_available", False)),
            brep_serialized=bool(d.get("brep_serialized", False)),
            confidence=str(d.get("confidence") or "derived"),  # type: ignore[arg-type]
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class TopologyElementIdentity:
    """Face/edge/solid identity that can be carried through picking and panels."""

    id: str
    shape_id: str
    kind: TopologyKind = "unknown"
    source_entity_id: str = ""
    parent_id: str = ""
    persistent_name: str = ""
    native_tag: str = ""
    bounds: tuple[float, float, float, float, float, float] | None = None
    material_id: str = ""
    phase_ids: list[str] = field(default_factory=list)
    role: str = ""
    confidence: IdentityConfidence = "derived"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"topology:{self.kind}:{self.shape_id}:{self.id}"

    @property
    def selection_kind(self) -> str:
        return "face" if self.kind == "face" else "edge" if self.kind == "edge" else "solid" if self.kind == "solid" else str(self.kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": TOPOLOGY_IDENTITY_CONTRACT,
            "key": self.key,
            "id": self.id,
            "topology_id": self.id,
            "shape_id": self.shape_id,
            "kind": self.kind,
            "source_entity_id": self.source_entity_id,
            "parent_id": self.parent_id,
            "persistent_name": self.persistent_name,
            "native_tag": self.native_tag,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "material_id": self.material_id,
            "phase_ids": list(self.phase_ids),
            "role": self.role,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "TopologyElementIdentity":
        d = dict(data or {})
        bounds = d.get("bounds")
        return cls(
            id=str(d.get("id") or d.get("topology_id") or ""),
            shape_id=str(d.get("shape_id") or ""),
            kind=str(d.get("kind") or d.get("topology_kind") or "unknown"),  # type: ignore[arg-type]
            source_entity_id=str(d.get("source_entity_id") or ""),
            parent_id=str(d.get("parent_id") or ""),
            persistent_name=str(d.get("persistent_name") or ""),
            native_tag=str(d.get("native_tag") or ""),
            bounds=None if bounds is None else tuple(float(v) for v in list(bounds)[:6]),  # type: ignore[arg-type]
            material_id=str(d.get("material_id") or ""),
            phase_ids=_ls(d.get("phase_ids")),
            role=str(d.get("role") or ""),
            confidence=str(d.get("confidence") or "derived"),  # type: ignore[arg-type]
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class SelectionStateIdentity:
    """Headless selection state shared by viewport, property panel and services."""

    active_key: str = ""
    selected_keys: list[str] = field(default_factory=list)
    active_topology_id: str = ""
    active_shape_id: str = ""
    active_entity_id: str = ""
    active_kind: str = "empty"
    source: str = "viewport"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_topology(self) -> bool:
        return bool(self.active_topology_id and self.active_kind in {"solid", "face", "edge"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": TOPOLOGY_IDENTITY_CONTRACT,
            "active_key": self.active_key,
            "selected_keys": list(self.selected_keys),
            "active_topology_id": self.active_topology_id,
            "active_shape_id": self.active_shape_id,
            "active_entity_id": self.active_entity_id,
            "active_kind": self.active_kind,
            "source": self.source,
            "has_topology": self.has_topology,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def empty(cls, *, source: str = "viewport", metadata: Mapping[str, Any] | None = None) -> "SelectionStateIdentity":
        return cls(source=source, metadata=_meta(metadata))

    @classmethod
    def from_topology(cls, topology: TopologyElementIdentity, *, selected_keys: Iterable[str] | None = None, source: str = "viewport", metadata: Mapping[str, Any] | None = None) -> "SelectionStateIdentity":
        keys = list(selected_keys or [topology.key])
        return cls(
            active_key=topology.key,
            selected_keys=keys,
            active_topology_id=topology.id,
            active_shape_id=topology.shape_id,
            active_entity_id=topology.source_entity_id,
            active_kind=str(topology.kind),
            source=source,
            metadata={**topology.to_dict(), **_meta(metadata)},
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SelectionStateIdentity":
        d = dict(data or {})
        return cls(
            active_key=str(d.get("active_key") or d.get("key") or ""),
            selected_keys=_ls(d.get("selected_keys")),
            active_topology_id=str(d.get("active_topology_id") or d.get("topology_id") or ""),
            active_shape_id=str(d.get("active_shape_id") or d.get("shape_id") or ""),
            active_entity_id=str(d.get("active_entity_id") or d.get("source_entity_id") or d.get("entity_id") or ""),
            active_kind=str(d.get("active_kind") or d.get("kind") or d.get("topology_kind") or "empty"),
            source=str(d.get("source") or "viewport"),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class OperationLineageIdentity:
    """Backend-neutral operation lineage between topology identity keys."""

    id: str
    operation_id: str
    operation_type: str = "unknown"
    input_keys: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    lineage_type: LineageKind = "derived"
    topology_kind: TopologyKind = "unknown"
    confidence: IdentityConfidence = "derived"
    native_history_available: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"lineage:{self.operation_id}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": TOPOLOGY_IDENTITY_CONTRACT,
            "key": self.key,
            "id": self.id,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "input_keys": list(self.input_keys),
            "output_keys": list(self.output_keys),
            "lineage_type": self.lineage_type,
            "topology_kind": self.topology_kind,
            "confidence": self.confidence,
            "native_history_available": bool(self.native_history_available),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "OperationLineageIdentity":
        d = dict(data or {})
        return cls(
            id=str(d.get("id") or "lineage"),
            operation_id=str(d.get("operation_id") or ""),
            operation_type=str(d.get("operation_type") or d.get("operation") or "unknown"),
            input_keys=_ls(d.get("input_keys")),
            output_keys=_ls(d.get("output_keys")),
            lineage_type=str(d.get("lineage_type") or "derived"),  # type: ignore[arg-type]
            topology_kind=str(d.get("topology_kind") or "unknown"),  # type: ignore[arg-type]
            confidence=str(d.get("confidence") or "derived"),  # type: ignore[arg-type]
            native_history_available=bool(d.get("native_history_available", False)),
            evidence=_meta(d.get("evidence")),
            metadata=_meta(d.get("metadata")),
        )


__all__ = [
    "TOPOLOGY_IDENTITY_CONTRACT",
    "IdentityConfidence",
    "LineageKind",
    "ModelEntityIdentity",
    "OperationLineageIdentity",
    "SelectionStateIdentity",
    "ShapeNodeIdentity",
    "TopologyElementIdentity",
    "TopologyKind",
]
