from __future__ import annotations

"""Post-boolean face lineage, split and merge history mapping."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geoproject.cad_shape_store import CadShapeStore, CadTopologyLineageRecord, CadTopologyRecord

BOOLEAN_TOPOLOGY_LINEAGE_CONTRACT = "geoai_simkit_boolean_topology_lineage_v1"

@dataclass(slots=True)
class BooleanTopologyLineageReport:
    contract: str = BOOLEAN_TOPOLOGY_LINEAGE_CONTRACT
    ok: bool = False
    status: str = "not_run"
    operation_count: int = 0
    lineage_count: int = 0
    face_lineage_count: int = 0
    split_count: int = 0
    merge_count: int = 0
    native_lineage_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"contract":self.contract,"ok":bool(self.ok),"status":self.status,"operation_count":self.operation_count,"lineage_count":self.lineage_count,"face_lineage_count":self.face_lineage_count,"split_count":self.split_count,"merge_count":self.merge_count,"native_lineage_count":self.native_lineage_count,"blockers":list(self.blockers),"warnings":list(self.warnings),"metadata":dict(self.metadata)}


def _same_kind(records: dict[str, CadTopologyRecord], ids: list[str], kind: str) -> list[CadTopologyRecord]:
    return [records[i] for i in ids if i in records and records[i].kind == kind]


def _name_key(record: CadTopologyRecord) -> str:
    if record.native_tag:
        return f"native:{record.kind}:{record.native_tag}"
    parts = (record.persistent_name or record.id).split("/")
    return f"{record.kind}:{parts[-1]}:{record.orientation}"


def _bounds_overlap(a: CadTopologyRecord, b: CadTopologyRecord) -> float:
    if a.bounds is None or b.bounds is None:
        return 0.0
    ax0, ax1, ay0, ay1, az0, az1 = a.bounds
    bx0, bx1, by0, by1, bz0, bz1 = b.bounds
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    iz = max(0.0, min(az1, bz1) - max(az0, bz0))
    # Planar faces may have zero thickness on one axis; add orientation-aware evidence.
    overlap = ix + iy + iz
    same_plane = a.orientation == b.orientation and any(abs(x-y) < 1e-9 for x,y in ((ax0,bx0),(ax1,bx1),(ay0,by0),(ay1,by1),(az0,bz0),(az1,bz1)))
    return overlap + (10.0 if same_plane else 0.0)


def _native_history_rows(store: CadShapeStore, op: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in (getattr(op, "metadata", {}) or {}, getattr(store, "metadata", {}) or {}):
        raw = dict(source).get("native_occ_history_map") or dict(source).get("occ_history_map") or []
        if isinstance(raw, dict):
            raw = raw.get(str(getattr(op, "id", ""))) or raw.get("rows") or []
        for row in list(raw or []):
            if not isinstance(row, dict):
                continue
            op_id = str(row.get("operation_id") or getattr(op, "id", ""))
            if op_id and op_id != str(getattr(op, "id", "")):
                continue
            inputs = [str(x) for x in list(row.get("input_topology_ids", row.get("inputs", [])) or []) if str(x) in store.topology_records]
            outputs = [str(x) for x in list(row.get("output_topology_ids", row.get("outputs", [])) or []) if str(x) in store.topology_records]
            if not outputs:
                continue
            rows.append({**dict(row), "input_topology_ids": inputs, "output_topology_ids": outputs})
    return rows


def build_boolean_topology_lineage(project: Any, *, overwrite: bool = False) -> BooleanTopologyLineageReport:
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        return BooleanTopologyLineageReport(ok=False, status="missing_cad_shape_store", blockers=["CadShapeStore is missing."])
    if overwrite:
        store.topology_lineage.clear()
    ops = [op for op in store.operation_history.values() if any(token in op.operation.lower() for token in ("boolean", "roundtrip", "fragment", "cut", "fuse", "subtract", "union"))]
    warnings: list[str] = []
    created = 0
    split = 0
    merge = 0
    for op in ops:
        input_topos: list[str] = []
        for sid in op.input_shape_ids:
            shape = store.shapes.get(sid)
            if shape:
                input_topos.extend(shape.topology_ids)
        output_topos: list[str] = []
        for sid in op.output_shape_ids:
            shape = store.shapes.get(sid)
            if shape:
                output_topos.extend(shape.topology_ids)
        # If operation history has no explicit shapes, infer pre/post by entity lists.
        if not input_topos:
            for shape in store.shapes.values():
                if any(e in op.input_entity_ids for e in shape.source_entity_ids):
                    input_topos.extend(shape.topology_ids)
        if not output_topos:
            for shape in store.shapes.values():
                if any(e in op.output_entity_ids for e in shape.source_entity_ids):
                    output_topos.extend(shape.topology_ids)
        native_rows = _native_history_rows(store, op)
        if native_rows:
            for row in native_rows:
                kind = str(row.get("topology_kind") or row.get("kind") or "unknown")
                lineage_type = str(row.get("lineage_type") or "native_history")
                lineage_id = f"lineage:{op.id}:native:{created:04d}"
                store.topology_lineage[lineage_id] = CadTopologyLineageRecord(
                    id=lineage_id,
                    operation_id=op.id,
                    input_topology_ids=list(row.get("input_topology_ids", [])),
                    output_topology_ids=list(row.get("output_topology_ids", [])),
                    lineage_type=lineage_type,
                    topology_kind=kind,
                    confidence="native",
                    native_backend_used=True,
                    evidence={"native_occ_history_map": True, **dict(row.get("evidence", {}) or {})},
                    metadata={"operation": op.operation, "backend": op.backend, "native_history_source": "OCC history map"},
                )
                if lineage_type == "split":
                    split += 1
                if lineage_type == "merge":
                    merge += 1
                created += 1
            continue
        if not input_topos or not output_topos:
            warnings.append(f"Operation {op.id} has incomplete input/output topology ids; lineage is recorded as generated-only.")
        for kind in ("solid", "face", "edge"):
            ins = _same_kind(store.topology_records, input_topos, kind)
            outs = _same_kind(store.topology_records, output_topos, kind)
            if not outs:
                continue
            input_by_key = { _name_key(t): t for t in ins }
            output_groups: dict[str, list[CadTopologyRecord]] = {}
            for out in outs:
                key = _name_key(out)
                output_groups.setdefault(key, []).append(out)
            for key, out_group in output_groups.items():
                matched_inputs: list[CadTopologyRecord] = []
                if key in input_by_key:
                    matched_inputs = [input_by_key[key]]
                elif ins:
                    best = sorted(ins, key=lambda x: _bounds_overlap(x, out_group[0]), reverse=True)
                    if best and _bounds_overlap(best[0], out_group[0]) > 0:
                        matched_inputs = [best[0]]
                lineage_type = "generated"
                if matched_inputs and len(out_group) == 1:
                    lineage_type = "preserved"
                elif matched_inputs and len(out_group) > 1:
                    lineage_type = "split"; split += 1
                elif len(matched_inputs) > 1 and len(out_group) == 1:
                    lineage_type = "merge"; merge += 1
                confidence = "native" if op.native_backend_used and any(store.topology_records.get(t.id, None) and t.native_tag for t in matched_inputs + out_group) else "derived"
                lineage_id = f"lineage:{op.id}:{kind}:{created:04d}"
                store.topology_lineage[lineage_id] = CadTopologyLineageRecord(
                    id=lineage_id,
                    operation_id=op.id,
                    input_topology_ids=[t.id for t in matched_inputs],
                    output_topology_ids=[t.id for t in out_group],
                    lineage_type=lineage_type,
                    topology_kind=kind,
                    confidence=confidence,
                    native_backend_used=bool(op.native_backend_used),
                    evidence={"match_key": key, "input_count": len(matched_inputs), "output_count": len(out_group)},
                    metadata={"operation": op.operation, "backend": op.backend},
                )
                created += 1
    store.metadata["last_boolean_topology_lineage"] = {"contract": BOOLEAN_TOPOLOGY_LINEAGE_CONTRACT, "lineage_count": len(store.topology_lineage), "operation_count": len(ops)}
    project.cad_shape_store = store
    project.metadata["release_1_4_5_boolean_topology_lineage"] = store.metadata["last_boolean_topology_lineage"]
    try:
        project.mark_changed(["cad_shape_store", "topology", "mesh", "solver", "result"])
    except Exception:
        pass
    records = list(store.topology_lineage.values())
    return BooleanTopologyLineageReport(ok=not bool(ops) or bool(created), status="lineage_built" if created else "no_boolean_operations", operation_count=len(ops), lineage_count=len(records), face_lineage_count=sum(1 for r in records if r.topology_kind == "face"), split_count=sum(1 for r in records if r.lineage_type == "split") + split, merge_count=sum(1 for r in records if r.lineage_type == "merge") + merge, native_lineage_count=sum(1 for r in records if r.confidence == "native"), warnings=warnings, metadata={"cad_shape_store_summary": store.summary()})


def validate_boolean_topology_lineage(project: Any, *, require_face_lineage: bool = True) -> dict[str, Any]:
    blockers: list[str] = []
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        return {"contract":"geoai_simkit_boolean_topology_lineage_validation_v1","ok":False,"blockers":["CadShapeStore is missing."]}
    if not store.topology_lineage:
        blockers.append("No topology lineage records are present.")
    if require_face_lineage and not any(r.topology_kind == "face" for r in store.topology_lineage.values()):
        blockers.append("No face lineage records are present.")
    bad = [r.id for r in store.topology_lineage.values() for tid in r.input_topology_ids + r.output_topology_ids if tid not in store.topology_records]
    if bad:
        blockers.append(f"Lineage references missing topology records: {bad[:3]}")
    return {"contract":"geoai_simkit_boolean_topology_lineage_validation_v1","ok":not blockers,"blockers":blockers,"lineage_count":len(store.topology_lineage),"face_lineage_count":sum(1 for r in store.topology_lineage.values() if r.topology_kind == "face"),"native_lineage_count":sum(1 for r in store.topology_lineage.values() if r.confidence == "native"),"summary":store.summary()}

__all__ = ["BooleanTopologyLineageReport", "build_boolean_topology_lineage", "validate_boolean_topology_lineage"]
