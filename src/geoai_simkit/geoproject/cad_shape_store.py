from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any, Mapping

CAD_SHAPE_STORE_CONTRACT = "geoproject_cad_shape_store_v1"

def stable_ref_hash(payload: Any) -> str:
    return sha1(repr(payload).encode("utf-8", errors="replace")).hexdigest()[:20]

def _ls(v: Any) -> list[str]:
    return [str(x) for x in list(v or [])]

@dataclass(slots=True)
class CadSerializedShapeReference:
    id: str
    backend: str = "cad_facade"
    shape_format: str = "brep_json"
    storage: str = "inline"
    path: str = ""
    digest: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self):
        return {"id":self.id,"backend":self.backend,"shape_format":self.shape_format,"storage":self.storage,"path":self.path,"digest":self.digest,"payload":dict(self.payload),"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","shape_ref")),str(d.get("backend","cad_facade")),str(d.get("shape_format",d.get("format","brep_json"))),str(d.get("storage","inline")),str(d.get("path","")),str(d.get("digest","")),dict(d.get("payload",{}) or {}),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadTopologyRecord:
    id: str
    shape_id: str
    kind: str
    source_entity_id: str=""
    parent_id: str=""
    persistent_name: str=""
    native_tag: str=""
    bounds: tuple[float,float,float,float,float,float]|None=None
    orientation: str=""
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self):
        return {"id":self.id,"shape_id":self.shape_id,"kind":self.kind,"source_entity_id":self.source_entity_id,"parent_id":self.parent_id,"persistent_name":self.persistent_name,"native_tag":self.native_tag,"bounds":list(self.bounds) if self.bounds is not None else None,"orientation":self.orientation,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {}); b=d.get("bounds")
        return cls(str(d.get("id","topology_record")),str(d.get("shape_id","")),str(d.get("kind","unknown")),str(d.get("source_entity_id","")),str(d.get("parent_id","")),str(d.get("persistent_name","")),str(d.get("native_tag","")),None if b is None else tuple(float(x) for x in list(b)[:6]),str(d.get("orientation","")),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadTopologyBinding:
    """Face/edge/solid level engineering binding record.

    This binding is intentionally independent from raw geometry ids.  It lets
    imported or boolean-generated CAD topology carry material, phase and role
    assignment after history operations have changed the original volumes.
    """
    id: str
    topology_id: str
    shape_id: str
    source_entity_id: str = ""
    topology_kind: str = "unknown"
    material_id: str = ""
    phase_ids: list[str] = field(default_factory=list)
    binding_scope: str = "topology"
    role: str = ""
    inherited_from: str = ""
    operation_id: str = ""
    confidence: str = "derived"
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"id":self.id,"topology_id":self.topology_id,"shape_id":self.shape_id,"source_entity_id":self.source_entity_id,"topology_kind":self.topology_kind,"material_id":self.material_id,"phase_ids":list(self.phase_ids),"binding_scope":self.binding_scope,"role":self.role,"inherited_from":self.inherited_from,"operation_id":self.operation_id,"confidence":self.confidence,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","topology_binding")),str(d.get("topology_id","")),str(d.get("shape_id","")),str(d.get("source_entity_id","")),str(d.get("topology_kind",d.get("kind","unknown"))),str(d.get("material_id","")),_ls(d.get("phase_ids",[])),str(d.get("binding_scope","topology")),str(d.get("role","")),str(d.get("inherited_from","")),str(d.get("operation_id","")),str(d.get("confidence","derived")),dict(d.get("metadata",{}) or {}))



@dataclass(slots=True)
class CadTopologyLineageRecord:
    """History mapping between pre/post-operation CAD topology.

    The record is intentionally backend-neutral.  Native OCC split/merge maps can
    store OCC tags in ``native_input_tags`` and ``native_output_tags``; surrogate
    or contract runs store deterministic persistent-name/bounds evidence with an
    explicit non-native confidence value.
    """
    id: str
    operation_id: str
    input_topology_ids: list[str] = field(default_factory=list)
    output_topology_ids: list[str] = field(default_factory=list)
    lineage_type: str = "derived"
    topology_kind: str = "unknown"
    confidence: str = "derived"
    native_backend_used: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"id":self.id,"operation_id":self.operation_id,"input_topology_ids":list(self.input_topology_ids),"output_topology_ids":list(self.output_topology_ids),"lineage_type":self.lineage_type,"topology_kind":self.topology_kind,"confidence":self.confidence,"native_backend_used":bool(self.native_backend_used),"evidence":dict(self.evidence),"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","topology_lineage")),str(d.get("operation_id","")),_ls(d.get("input_topology_ids",[])),_ls(d.get("output_topology_ids",[])),str(d.get("lineage_type","derived")),str(d.get("topology_kind","unknown")),str(d.get("confidence","derived")),bool(d.get("native_backend_used",False)),dict(d.get("evidence",{}) or {}),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadEntityBinding:
    id: str
    entity_id: str
    entity_type: str
    shape_id: str
    topology_ids: list[str]=field(default_factory=list)
    binding_role: str="owns_shape"
    material_id: str=""
    phase_ids: list[str]=field(default_factory=list)
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self):
        return {"id":self.id,"entity_id":self.entity_id,"entity_type":self.entity_type,"shape_id":self.shape_id,"topology_ids":list(self.topology_ids),"binding_role":self.binding_role,"material_id":self.material_id,"phase_ids":list(self.phase_ids),"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","binding")),str(d.get("entity_id","")),str(d.get("entity_type","")),str(d.get("shape_id","")),_ls(d.get("topology_ids",[])),str(d.get("binding_role","owns_shape")),str(d.get("material_id","")),_ls(d.get("phase_ids",[])),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadOperationHistoryRecord:
    id: str
    operation: str
    input_shape_ids: list[str]=field(default_factory=list)
    output_shape_ids: list[str]=field(default_factory=list)
    input_entity_ids: list[str]=field(default_factory=list)
    output_entity_ids: list[str]=field(default_factory=list)
    backend: str="cad_facade"
    native_backend_used: bool=False
    fallback_used: bool=True
    status: str="recorded"
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self):
        return {"id":self.id,"operation":self.operation,"input_shape_ids":list(self.input_shape_ids),"output_shape_ids":list(self.output_shape_ids),"input_entity_ids":list(self.input_entity_ids),"output_entity_ids":list(self.output_entity_ids),"backend":self.backend,"native_backend_used":bool(self.native_backend_used),"fallback_used":bool(self.fallback_used),"status":self.status,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","operation")),str(d.get("operation","unknown")),_ls(d.get("input_shape_ids",[])),_ls(d.get("output_shape_ids",[])),_ls(d.get("input_entity_ids",[])),_ls(d.get("output_entity_ids",[])),str(d.get("backend","cad_facade")),bool(d.get("native_backend_used",False)),bool(d.get("fallback_used",True)),str(d.get("status","recorded")),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadShapeRecord:
    id: str
    name: str
    kind: str="solid"
    source_entity_ids: list[str]=field(default_factory=list)
    serialized_ref_id: str=""
    backend: str="cad_facade"
    native_shape_available: bool=False
    brep_serialized: bool=False
    topology_ids: list[str]=field(default_factory=list)
    material_id: str=""
    phase_ids: list[str]=field(default_factory=list)
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self):
        return {"id":self.id,"name":self.name,"kind":self.kind,"source_entity_ids":list(self.source_entity_ids),"serialized_ref_id":self.serialized_ref_id,"backend":self.backend,"native_shape_available":bool(self.native_shape_available),"brep_serialized":bool(self.brep_serialized),"topology_ids":list(self.topology_ids),"material_id":self.material_id,"phase_ids":list(self.phase_ids),"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        return cls(str(d.get("id","shape")),str(d.get("name",d.get("id","shape"))),str(d.get("kind","solid")),_ls(d.get("source_entity_ids",[])),str(d.get("serialized_ref_id","")),str(d.get("backend","cad_facade")),bool(d.get("native_shape_available",False)),bool(d.get("brep_serialized",False)),_ls(d.get("topology_ids",[])),str(d.get("material_id","")),_ls(d.get("phase_ids",[])),dict(d.get("metadata",{}) or {}))

@dataclass(slots=True)
class CadShapeStore:
    contract: str=CAD_SHAPE_STORE_CONTRACT
    shapes: dict[str,CadShapeRecord]=field(default_factory=dict)
    serialized_refs: dict[str,CadSerializedShapeReference]=field(default_factory=dict)
    topology_records: dict[str,CadTopologyRecord]=field(default_factory=dict)
    entity_bindings: dict[str,CadEntityBinding]=field(default_factory=dict)
    topology_bindings: dict[str,CadTopologyBinding]=field(default_factory=dict)
    topology_lineage: dict[str,CadTopologyLineageRecord]=field(default_factory=dict)
    operation_history: dict[str,CadOperationHistoryRecord]=field(default_factory=dict)
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self):
        return {"contract":self.contract,"Shapes":[x.to_dict() for x in self.shapes.values()],"SerializedShapeReferences":[x.to_dict() for x in self.serialized_refs.values()],"TopologyRecords":[x.to_dict() for x in self.topology_records.values()],"EntityBindings":[x.to_dict() for x in self.entity_bindings.values()],"TopologyBindings":[x.to_dict() for x in self.topology_bindings.values()],"TopologyLineage":[x.to_dict() for x in self.topology_lineage.values()],"OperationHistory":[x.to_dict() for x in self.operation_history.values()],"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d:Mapping[str,Any]|None):
        d=dict(d or {})
        sh=[CadShapeRecord.from_dict(x) for x in list(d.get("Shapes",d.get("shapes",[])) or [])]
        refs=[CadSerializedShapeReference.from_dict(x) for x in list(d.get("SerializedShapeReferences",d.get("serialized_refs",[])) or [])]
        topo=[CadTopologyRecord.from_dict(x) for x in list(d.get("TopologyRecords",d.get("topology_records",[])) or [])]
        binds=[CadEntityBinding.from_dict(x) for x in list(d.get("EntityBindings",d.get("entity_bindings",[])) or [])]
        topobinds=[CadTopologyBinding.from_dict(x) for x in list(d.get("TopologyBindings",d.get("topology_bindings",[])) or [])]
        lineage=[CadTopologyLineageRecord.from_dict(x) for x in list(d.get("TopologyLineage",d.get("topology_lineage",[])) or [])]
        ops=[CadOperationHistoryRecord.from_dict(x) for x in list(d.get("OperationHistory",d.get("operation_history",[])) or [])]
        return cls(str(d.get("contract",CAD_SHAPE_STORE_CONTRACT)),{x.id:x for x in sh},{x.id:x for x in refs},{x.id:x for x in topo},{x.id:x for x in binds},{x.id:x for x in topobinds},{x.id:x for x in lineage},{x.id:x for x in ops},dict(d.get("metadata",{}) or {}))
    def summary(self):
        return {"contract":self.contract,"shape_count":len(self.shapes),"serialized_ref_count":len(self.serialized_refs),"topology_record_count":len(self.topology_records),"entity_binding_count":len(self.entity_bindings),"topology_binding_count":len(self.topology_bindings),"operation_count":len(self.operation_history),"topology_lineage_count":len(self.topology_lineage),"native_shape_count":sum(1 for x in self.shapes.values() if x.native_shape_available),"brep_serialized_count":sum(1 for x in self.shapes.values() if x.brep_serialized),"native_brep_certified_count":sum(1 for x in self.shapes.values() if bool(x.metadata.get("native_brep_certified"))),"face_binding_count":sum(1 for x in self.topology_bindings.values() if x.topology_kind == "face"),"edge_binding_count":sum(1 for x in self.topology_bindings.values() if x.topology_kind == "edge"),"metadata":dict(self.metadata)}
