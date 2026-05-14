from __future__ import annotations

"""Face/edge/material/phase binding after CAD boolean and import history.

This service binds CadShapeStore topology records (solid/face/edge/vertex) to
engineering material and construction phase semantics.  It consumes entity
bindings and operation history, so imported solids and boolean-generated volumes
can keep useful assignments even after original GeoProject volume ids change.
"""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geoproject.cad_shape_store import CadShapeStore, CadTopologyBinding

TOPOLOGY_BINDING_CONTRACT = "geoai_simkit_face_edge_material_phase_binding_v1"


@dataclass(slots=True)
class TopologyBindingReport:
    contract: str = TOPOLOGY_BINDING_CONTRACT
    ok: bool = False
    status: str = "not_run"
    shape_count: int = 0
    topology_record_count: int = 0
    binding_count: int = 0
    solid_binding_count: int = 0
    face_binding_count: int = 0
    edge_binding_count: int = 0
    phase_binding_count: int = 0
    material_binding_count: int = 0
    operation_history_count: int = 0
    inherited_binding_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "status": self.status,
            "shape_count": self.shape_count,
            "topology_record_count": self.topology_record_count,
            "binding_count": self.binding_count,
            "solid_binding_count": self.solid_binding_count,
            "face_binding_count": self.face_binding_count,
            "edge_binding_count": self.edge_binding_count,
            "phase_binding_count": self.phase_binding_count,
            "material_binding_count": self.material_binding_count,
            "operation_history_count": self.operation_history_count,
            "inherited_binding_count": self.inherited_binding_count,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _active_phase_ids_for_entity(project: Any, entity_id: str) -> list[str]:
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


def _material_for_entity(project: Any, entity_id: str, fallback: str = "") -> str:
    geom = getattr(project, "geometry_model", None)
    vol = None if geom is None else getattr(geom, "volumes", {}).get(entity_id)
    mat = getattr(vol, "material_id", None) if vol is not None else None
    return str(mat or fallback or "")


def _role_for_entity(project: Any, entity_id: str) -> str:
    geom = getattr(project, "geometry_model", None)
    vol = None if geom is None else getattr(geom, "volumes", {}).get(entity_id)
    return str(getattr(vol, "role", "") or "")


def _operation_for_shape(store: CadShapeStore, shape_id: str) -> str:
    for op in store.operation_history.values():
        if shape_id in list(op.output_shape_ids or []):
            return op.id
    return ""


def bind_topology_material_phase(
    project: Any,
    *,
    include_faces: bool = True,
    include_edges: bool = True,
    include_solids: bool = True,
    overwrite: bool = True,
) -> TopologyBindingReport:
    blockers: list[str] = []
    warnings: list[str] = []
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        return TopologyBindingReport(ok=False, status="missing_cad_shape_store", blockers=["CadShapeStore is missing on project."])
    if not store.shapes:
        blockers.append("CadShapeStore has no shapes to bind.")
    if not store.topology_records:
        blockers.append("CadShapeStore has no topology records to bind.")
    if blockers:
        return TopologyBindingReport(ok=False, status="blocked", blockers=blockers)
    if overwrite:
        store.topology_bindings.clear()
    inherited = 0
    for shape in store.shapes.values():
        source_entity_id = next(iter(shape.source_entity_ids or []), "")
        material_id = str(shape.material_id or _material_for_entity(project, source_entity_id))
        phase_ids = sorted(set(list(shape.phase_ids or []) + _active_phase_ids_for_entity(project, source_entity_id)))
        role = _role_for_entity(project, source_entity_id)
        op_id = _operation_for_shape(store, shape.id)
        if not material_id:
            warnings.append(f"Shape {shape.id} / entity {source_entity_id} has no material binding.")
        for tid in shape.topology_ids:
            topo = store.topology_records.get(tid)
            if topo is None:
                warnings.append(f"Shape {shape.id} references missing topology record {tid}.")
                continue
            if topo.kind == "solid" and not include_solids:
                continue
            if topo.kind == "face" and not include_faces:
                continue
            if topo.kind == "edge" and not include_edges:
                continue
            if topo.kind not in {"solid", "face", "edge"}:
                continue
            bid = f"binding:{shape.id}:{topo.kind}:{tid.split(':')[-1]}"
            inherited_from = source_entity_id or shape.id
            confidence = "native" if bool(shape.metadata.get("native_brep_certified")) and bool(topo.metadata.get("native_topology")) else "derived"
            store.topology_bindings[bid] = CadTopologyBinding(
                id=bid,
                topology_id=tid,
                shape_id=shape.id,
                source_entity_id=source_entity_id,
                topology_kind=topo.kind,
                material_id=material_id,
                phase_ids=phase_ids,
                binding_scope=f"{topo.kind}_material_phase",
                role=role,
                inherited_from=inherited_from,
                operation_id=op_id,
                confidence=confidence,
                metadata={
                    "persistent_name": topo.persistent_name,
                    "native_tag": topo.native_tag,
                    "orientation": topo.orientation,
                    "shape_backend": shape.backend,
                    "native_brep_certified": bool(shape.metadata.get("native_brep_certified")),
                    "operation_history_id": op_id,
                    "topology_identity_key": f"topology:{topo.kind}:{shape.id}:{tid}",
                    "selection_key": f"topology:{topo.kind}:{shape.id}:{tid}",
                },
            )
            inherited += 1
    summary = store.summary()
    store.metadata["last_topology_material_phase_binding"] = {
        "contract": TOPOLOGY_BINDING_CONTRACT,
        "binding_count": len(store.topology_bindings),
        "summary": summary,
    }
    project.cad_shape_store = store
    project.metadata["release_1_4_4_topology_material_phase_binding"] = store.metadata["last_topology_material_phase_binding"]
    try:
        project.mark_changed(["cad_shape_store", "geometry", "materials", "phases", "mesh", "solver", "result"])
    except Exception:
        pass
    bindings = list(store.topology_bindings.values())
    return TopologyBindingReport(
        ok=True,
        status="bound",
        shape_count=len(store.shapes),
        topology_record_count=len(store.topology_records),
        binding_count=len(bindings),
        solid_binding_count=sum(1 for b in bindings if b.topology_kind == "solid"),
        face_binding_count=sum(1 for b in bindings if b.topology_kind == "face"),
        edge_binding_count=sum(1 for b in bindings if b.topology_kind == "edge"),
        phase_binding_count=sum(1 for b in bindings if b.phase_ids),
        material_binding_count=sum(1 for b in bindings if b.material_id),
        operation_history_count=len(store.operation_history),
        inherited_binding_count=inherited,
        warnings=warnings,
        metadata={"cad_shape_store_summary": summary},
    )


def validate_topology_material_phase_bindings(project: Any, *, require_face_bindings: bool = True, require_phase_bindings: bool = True) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        return {"contract": "geoai_simkit_face_edge_material_phase_binding_validation_v1", "ok": False, "blockers": ["CadShapeStore is missing."], "warnings": []}
    if not store.topology_bindings:
        blockers.append("No topology material/phase bindings are present.")
    if require_face_bindings and not any(b.topology_kind == "face" for b in store.topology_bindings.values()):
        blockers.append("No face-level topology bindings are present.")
    if require_phase_bindings and not any(b.phase_ids for b in store.topology_bindings.values()):
        blockers.append("No topology binding contains phase ids.")
    missing_topo = [b.id for b in store.topology_bindings.values() if b.topology_id not in store.topology_records]
    if missing_topo:
        blockers.append(f"Topology bindings reference missing topology records: {missing_topo[:3]}.")
    missing_shape = [b.id for b in store.topology_bindings.values() if b.shape_id not in store.shapes]
    if missing_shape:
        blockers.append(f"Topology bindings reference missing shapes: {missing_shape[:3]}.")
    if not any(b.material_id for b in store.topology_bindings.values()):
        warnings.append("Topology bindings exist but none carry material ids.")
    return {
        "contract": "geoai_simkit_face_edge_material_phase_binding_validation_v1",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "binding_count": len(store.topology_bindings),
        "face_binding_count": sum(1 for b in store.topology_bindings.values() if b.topology_kind == "face"),
        "edge_binding_count": sum(1 for b in store.topology_bindings.values() if b.topology_kind == "edge"),
        "material_binding_count": sum(1 for b in store.topology_bindings.values() if b.material_id),
        "phase_binding_count": sum(1 for b in store.topology_bindings.values() if b.phase_ids),
        "summary": store.summary(),
    }


__all__ = ["TopologyBindingReport", "bind_topology_material_phase", "validate_topology_material_phase_bindings"]


def assign_topology_material_phase(
    project: Any,
    topology_id: str,
    *,
    material_id: str | None = None,
    phase_ids: list[str] | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """Assign material/phase data directly to a selected face/edge/solid topology.

    This is the service used by GUI face/edge property editing.  It creates or
    updates a CadTopologyBinding without requiring users to edit source volumes.
    """
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        return {"contract":"geoai_simkit_direct_topology_assignment_v1","ok":False,"status":"missing_cad_shape_store","blockers":["CadShapeStore is missing."]}
    topo = store.topology_records.get(str(topology_id))
    if topo is None:
        return {"contract":"geoai_simkit_direct_topology_assignment_v1","ok":False,"status":"missing_topology","blockers":[f"Topology record not found: {topology_id}"]}
    bid = f"binding:{topo.shape_id}:{topo.kind}:{topo.id.split(':')[-1]}"
    existing = store.topology_bindings.get(bid)
    if existing is None:
        existing = CadTopologyBinding(id=bid, topology_id=topo.id, shape_id=topo.shape_id, source_entity_id=topo.source_entity_id, topology_kind=topo.kind, binding_scope=f"{topo.kind}_direct_gui_assignment", metadata={"persistent_name": topo.persistent_name, "native_tag": topo.native_tag})
    if material_id is not None:
        existing.material_id = str(material_id)
    if phase_ids is not None:
        existing.phase_ids = sorted(set(str(x) for x in phase_ids))
    if role is not None:
        existing.role = str(role)
    existing.confidence = "user_assigned"
    existing.metadata.update({"assigned_from_gui": True, "persistent_name": topo.persistent_name, "native_tag": topo.native_tag})
    store.topology_bindings[bid] = existing
    store.metadata["last_direct_topology_assignment"] = {"topology_id": topo.id, "binding_id": bid, "material_id": existing.material_id, "phase_ids": list(existing.phase_ids)}
    project.cad_shape_store = store
    project.metadata["release_1_4_5_direct_topology_assignment"] = store.metadata["last_direct_topology_assignment"]
    try:
        project.mark_changed(["cad_shape_store", "materials", "phases", "mesh", "solver", "result"], action="assign_topology_material_phase", affected_entities=[topo.source_entity_id or topo.shape_id])
    except Exception:
        pass
    return {"contract":"geoai_simkit_direct_topology_assignment_v1","ok":True,"status":"assigned","binding":existing.to_dict(),"topology":topo.to_dict()}

__all__.append("assign_topology_material_phase")
