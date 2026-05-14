from __future__ import annotations

"""Build and resolve the project-wide topology identity index.

This service is intentionally headless.  It consumes GeoProject/CadShapeStore
records and produces a compact identity index used by GUI selection, material
and phase assignment, operation lineage and future meshing physical groups.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from geoai_simkit.core.topology_identity import (
    TOPOLOGY_IDENTITY_CONTRACT,
    ModelEntityIdentity,
    OperationLineageIdentity,
    SelectionStateIdentity,
    ShapeNodeIdentity,
    TopologyElementIdentity,
)
from geoai_simkit.geoproject.cad_shape_store import CadShapeStore


@dataclass(slots=True)
class TopologyIdentityIndex:
    contract: str = TOPOLOGY_IDENTITY_CONTRACT
    entities: dict[str, ModelEntityIdentity] = field(default_factory=dict)
    shapes: dict[str, ShapeNodeIdentity] = field(default_factory=dict)
    topology: dict[str, TopologyElementIdentity] = field(default_factory=dict)
    lineage: dict[str, OperationLineageIdentity] = field(default_factory=dict)
    lookup_by_topology_id: dict[str, str] = field(default_factory=dict)
    lookup_by_shape_id: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "entities": [item.to_dict() for item in self.entities.values()],
            "shapes": [item.to_dict() for item in self.shapes.values()],
            "topology": [item.to_dict() for item in self.topology.values()],
            "lineage": [item.to_dict() for item in self.lineage.values()],
            "lookup_by_topology_id": dict(self.lookup_by_topology_id),
            "lookup_by_shape_id": dict(self.lookup_by_shape_id),
            "summary": self.summary(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "TopologyIdentityIndex":
        d = dict(data or {})
        entities = [ModelEntityIdentity.from_dict(x) for x in list(d.get("entities", []) or [])]
        shapes = [ShapeNodeIdentity.from_dict(x) for x in list(d.get("shapes", []) or [])]
        topology = [TopologyElementIdentity.from_dict(x) for x in list(d.get("topology", []) or [])]
        lineage = [OperationLineageIdentity.from_dict(x) for x in list(d.get("lineage", []) or [])]
        index = cls(
            contract=str(d.get("contract") or TOPOLOGY_IDENTITY_CONTRACT),
            entities={item.key: item for item in entities},
            shapes={item.key: item for item in shapes},
            topology={item.key: item for item in topology},
            lineage={item.key: item for item in lineage},
            lookup_by_topology_id={str(k): str(v) for k, v in dict(d.get("lookup_by_topology_id", {}) or {}).items()},
            lookup_by_shape_id={str(k): str(v) for k, v in dict(d.get("lookup_by_shape_id", {}) or {}).items()},
            metadata=dict(d.get("metadata", {}) or {}),
        )
        if not index.lookup_by_topology_id:
            index.lookup_by_topology_id = {item.id: item.key for item in topology}
        if not index.lookup_by_shape_id:
            index.lookup_by_shape_id = {item.id: item.key for item in shapes}
        return index

    def summary(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "entity_count": len(self.entities),
            "shape_count": len(self.shapes),
            "topology_count": len(self.topology),
            "solid_count": sum(1 for item in self.topology.values() if item.kind == "solid"),
            "face_count": sum(1 for item in self.topology.values() if item.kind == "face"),
            "edge_count": sum(1 for item in self.topology.values() if item.kind == "edge"),
            "lineage_count": len(self.lineage),
            "native_topology_count": sum(1 for item in self.topology.values() if item.confidence in {"native", "certified"}),
        }

    def topology_by_id(self, topology_id: str) -> TopologyElementIdentity | None:
        key = self.lookup_by_topology_id.get(str(topology_id))
        return self.topology.get(key or "")

    def shape_by_id(self, shape_id: str) -> ShapeNodeIdentity | None:
        key = self.lookup_by_shape_id.get(str(shape_id))
        return self.shapes.get(key or "")

    def resolve_pick_metadata(self, metadata: Mapping[str, Any] | None) -> SelectionStateIdentity:
        d = dict(metadata or {})
        topology_id = str(d.get("topology_id") or d.get("active_topology_id") or d.get("id") or "")
        if topology_id:
            topo = self.topology_by_id(topology_id)
            if topo is not None:
                return SelectionStateIdentity.from_topology(topo, metadata={"pick_metadata": d})
        key = str(d.get("topology_identity_key") or d.get("active_key") or d.get("key") or "")
        topo = self.topology.get(key)
        if topo is not None:
            return SelectionStateIdentity.from_topology(topo, metadata={"pick_metadata": d})
        return SelectionStateIdentity.empty(metadata={"pick_metadata": d})


def _phase_ids_for_entity(project: Any, entity_id: str) -> list[str]:
    phase_ids: list[str] = []
    phase_manager = getattr(project, "phase_manager", None)
    snapshots = getattr(phase_manager, "phase_state_snapshots", {}) or {}
    for sid, snap in snapshots.items():
        if entity_id in list(getattr(snap, "active_volume_ids", []) or []):
            phase_ids.append(str(sid))
    if not phase_ids and phase_manager is not None:
        initial = getattr(getattr(phase_manager, "initial_phase", None), "id", "initial")
        phase_ids.append(str(initial or "initial"))
    return sorted(set(phase_ids))


def _entity_identity(project: Any, entity_id: str, *, source: str = "geoproject") -> ModelEntityIdentity:
    geom = getattr(project, "geometry_model", None)
    vol = None if geom is None else getattr(geom, "volumes", {}).get(entity_id)
    return ModelEntityIdentity(
        id=entity_id,
        entity_type="volume",
        source=source,
        display_name=str(getattr(vol, "name", "") or entity_id),
        material_id=str(getattr(vol, "material_id", "") or ""),
        phase_ids=_phase_ids_for_entity(project, entity_id),
        role=str(getattr(vol, "role", "") or ""),
        metadata=getattr(vol, "to_dict", lambda: {})() if vol is not None else {},
    )


def _binding_by_topology_id(store: CadShapeStore) -> dict[str, Any]:
    return {str(b.topology_id): b for b in getattr(store, "topology_bindings", {}).values()}


def _topology_key(topology_id: str, shape_id: str, kind: str) -> str:
    return f"topology:{kind}:{shape_id}:{topology_id}"


def build_topology_identity_index(project: Any, *, attach: bool = True) -> TopologyIdentityIndex:
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        index = TopologyIdentityIndex(metadata={"status": "missing_cad_shape_store"})
        if attach:
            try:
                project.metadata["topology_identity_index"] = index.to_dict()
            except Exception:
                pass
        return index

    index = TopologyIdentityIndex(metadata={"status": "built", "cad_shape_store_contract": getattr(store, "contract", "")})
    bindings = _binding_by_topology_id(store)

    for shape in store.shapes.values():
        confidence = "certified" if bool(shape.metadata.get("native_brep_certified")) else "native" if shape.native_shape_available else "derived"
        shape_identity = ShapeNodeIdentity(
            id=shape.id,
            kind=shape.kind,
            backend=shape.backend,
            source_entity_ids=list(shape.source_entity_ids),
            native_shape_available=bool(shape.native_shape_available),
            brep_serialized=bool(shape.brep_serialized),
            confidence=confidence,  # type: ignore[arg-type]
            metadata={**dict(shape.metadata), "serialized_ref_id": shape.serialized_ref_id},
        )
        index.shapes[shape_identity.key] = shape_identity
        index.lookup_by_shape_id[shape.id] = shape_identity.key
        for entity_id in shape.source_entity_ids:
            entity = _entity_identity(project, str(entity_id))
            index.entities[entity.key] = entity

    for topo in store.topology_records.values():
        shape = store.shapes.get(topo.shape_id)
        source_entity_id = str(topo.source_entity_id or "")
        if not source_entity_id and shape is not None and shape.source_entity_ids:
            source_entity_id = str(shape.source_entity_ids[0])
        if source_entity_id:
            entity = _entity_identity(project, source_entity_id)
            index.entities[entity.key] = entity
        binding = bindings.get(topo.id)
        confidence = "native" if bool(topo.metadata.get("native_topology")) or bool(topo.native_tag) else "certified" if shape is not None and bool(shape.metadata.get("native_brep_certified")) else "derived"
        identity = TopologyElementIdentity(
            id=topo.id,
            shape_id=topo.shape_id,
            kind=topo.kind,  # type: ignore[arg-type]
            source_entity_id=source_entity_id,
            parent_id=topo.parent_id,
            persistent_name=topo.persistent_name,
            native_tag=topo.native_tag,
            bounds=topo.bounds,
            material_id=str(getattr(binding, "material_id", "") or getattr(shape, "material_id", "") or ""),
            phase_ids=list(getattr(binding, "phase_ids", []) or getattr(shape, "phase_ids", []) or _phase_ids_for_entity(project, source_entity_id)),
            role=str(getattr(binding, "role", "") or ""),
            confidence=confidence,  # type: ignore[arg-type]
            metadata={
                **dict(topo.metadata),
                "shape_id": topo.shape_id,
                "topology_id": topo.id,
                "topology_kind": topo.kind,
                "source_entity_id": source_entity_id,
                "binding_id": str(getattr(binding, "id", "") or ""),
                "material_id": str(getattr(binding, "material_id", "") or ""),
                "phase_ids": list(getattr(binding, "phase_ids", []) or []),
            },
        )
        index.topology[identity.key] = identity
        index.lookup_by_topology_id[topo.id] = identity.key

    for row in store.topology_lineage.values():
        input_keys = [_topology_key(tid, store.topology_records[tid].shape_id, store.topology_records[tid].kind) for tid in row.input_topology_ids if tid in store.topology_records]
        output_keys = [_topology_key(tid, store.topology_records[tid].shape_id, store.topology_records[tid].kind) for tid in row.output_topology_ids if tid in store.topology_records]
        op = store.operation_history.get(row.operation_id)
        lineage = OperationLineageIdentity(
            id=row.id,
            operation_id=row.operation_id,
            operation_type=str(getattr(op, "operation", "") or row.metadata.get("operation", "unknown")),
            input_keys=input_keys,
            output_keys=output_keys,
            lineage_type=row.lineage_type,  # type: ignore[arg-type]
            topology_kind=row.topology_kind,  # type: ignore[arg-type]
            confidence=row.confidence,  # type: ignore[arg-type]
            native_history_available=bool(row.native_backend_used and row.confidence == "native"),
            evidence=dict(row.evidence),
            metadata=dict(row.metadata),
        )
        index.lineage[lineage.key] = lineage

    if attach:
        snapshot = index.to_dict()
        store.metadata["topology_identity_index"] = snapshot
        try:
            project.metadata["topology_identity_index"] = snapshot
            project.cad_shape_store = store
            project.mark_changed(["cad_shape_store", "selection", "topology", "mesh", "solver", "result"])
        except Exception:
            pass
    return index


def resolve_topology_selection(project: Any, metadata: Mapping[str, Any] | None = None, *, index: TopologyIdentityIndex | None = None) -> SelectionStateIdentity:
    idx = index or build_topology_identity_index(project, attach=False)
    return idx.resolve_pick_metadata(metadata)


def validate_topology_identity_index(project: Any, *, require_faces: bool = True, require_edges: bool = True) -> dict[str, Any]:
    index = build_topology_identity_index(project, attach=False)
    summary = index.summary()
    blockers: list[str] = []
    if not index.shapes:
        blockers.append("No shape identities are present.")
    if not index.topology:
        blockers.append("No topology element identities are present.")
    if require_faces and summary["face_count"] <= 0:
        blockers.append("No face topology identities are present.")
    if require_edges and summary["edge_count"] <= 0:
        blockers.append("No edge topology identities are present.")
    missing_shape = [item.id for item in index.topology.values() if item.shape_id not in index.lookup_by_shape_id]
    if missing_shape:
        blockers.append(f"Topology identities reference missing shapes: {missing_shape[:3]}.")
    return {"contract": TOPOLOGY_IDENTITY_CONTRACT, "ok": not blockers, "blockers": blockers, "summary": summary}


__all__ = [
    "TopologyIdentityIndex",
    "build_topology_identity_index",
    "resolve_topology_selection",
    "validate_topology_identity_index",
]
