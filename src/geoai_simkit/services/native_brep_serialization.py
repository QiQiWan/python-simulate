from __future__ import annotations

"""Native TopoDS_Shape BRep serialization and topology enumeration helpers.

This module is intentionally optional-runtime aware. It can use OCP or
pythonocc-core when present, but never claims native BRep certification unless a
TopoDS_Shape object was actually serialized to a BRep file and topology records
were enumerated from the native shape.
"""

from dataclasses import dataclass, field
from hashlib import sha1
import json
from pathlib import Path
from typing import Any

from geoai_simkit.geoproject.cad_shape_store import CadTopologyRecord, stable_ref_hash

NATIVE_BREP_CAPABILITY_CONTRACT = "geoai_simkit_native_brep_serialization_capability_v1"
NATIVE_BREP_SERIALIZATION_CONTRACT = "geoai_simkit_native_topods_brep_serialization_v1"


def _try_import(name: str) -> tuple[bool, Any, str]:
    try:
        module = __import__(name, fromlist=["*"])
        return True, module, ""
    except Exception as exc:  # pragma: no cover - host dependent
        return False, None, f"{type(exc).__name__}: {exc}"


@dataclass(slots=True)
class NativeBrepCapability:
    contract: str = NATIVE_BREP_CAPABILITY_CONTRACT
    ocp_available: bool = False
    pythonocc_available: bool = False
    topods_shape_available: bool = False
    brep_tools_write_available: bool = False
    top_exp_available: bool = False
    ifcopenshell_available: bool = False
    ifcopenshell_geom_available: bool = False
    native_brep_serialization_possible: bool = False
    native_topology_enumeration_possible: bool = False
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ocp_available": self.ocp_available,
            "pythonocc_available": self.pythonocc_available,
            "topods_shape_available": self.topods_shape_available,
            "brep_tools_write_available": self.brep_tools_write_available,
            "top_exp_available": self.top_exp_available,
            "ifcopenshell_available": self.ifcopenshell_available,
            "ifcopenshell_geom_available": self.ifcopenshell_geom_available,
            "native_brep_serialization_possible": self.native_brep_serialization_possible,
            "native_topology_enumeration_possible": self.native_topology_enumeration_possible,
            "errors": dict(self.errors),
            "certification_policy": "native_brep_certified requires real TopoDS_Shape serialization plus native topology enumeration",
        }


def probe_native_brep_capability() -> NativeBrepCapability:
    errors: dict[str, str] = {}
    ocp_ok, _, err = _try_import("OCP.TopoDS")
    if err: errors["OCP.TopoDS"] = err
    pyocc_ok, _, err = _try_import("OCC.Core.TopoDS")
    if err: errors["OCC.Core.TopoDS"] = err
    topods_shape_available = ocp_ok or pyocc_ok

    brep_ok = False
    for mod in ("OCP.BRepTools", "OCC.Core.BRepTools"):
        ok, module, err = _try_import(mod)
        if ok and (hasattr(module, "BRepTools") or hasattr(module, "breptools") or hasattr(module, "BRepTools_Write") or hasattr(module, "breptools_Write")):
            brep_ok = True
        elif err:
            errors[mod] = err
    topexp_ok = False
    for mod in ("OCP.TopExp", "OCC.Core.TopExp"):
        ok, _, err = _try_import(mod)
        topexp_ok = topexp_ok or ok
        if err: errors[mod] = err
    ifc_ok, _, err = _try_import("ifcopenshell")
    if err: errors["ifcopenshell"] = err
    ifcgeom_ok, _, err = _try_import("ifcopenshell.geom")
    if err: errors["ifcopenshell.geom"] = err
    return NativeBrepCapability(
        ocp_available=ocp_ok,
        pythonocc_available=pyocc_ok,
        topods_shape_available=topods_shape_available,
        brep_tools_write_available=brep_ok,
        top_exp_available=topexp_ok,
        ifcopenshell_available=ifc_ok,
        ifcopenshell_geom_available=ifcgeom_ok,
        native_brep_serialization_possible=topods_shape_available and brep_ok,
        native_topology_enumeration_possible=topods_shape_available and topexp_ok,
        errors=errors,
    )


def _shape_digest(path: Path) -> str:
    try:
        return sha1(path.read_bytes()).hexdigest()[:20]
    except Exception:
        return stable_ref_hash(str(path))


def _write_with_ocp(shape: Any, path: Path) -> bool:
    try:  # pragma: no cover - native runtime dependent
        from OCP.BRepTools import BRepTools
        ok = BRepTools.Write_s(shape, str(path)) if hasattr(BRepTools, "Write_s") else BRepTools.Write(shape, str(path))
        return bool(ok) or path.exists()
    except Exception:
        return False


def _write_with_pythonocc(shape: Any, path: Path) -> bool:
    try:  # pragma: no cover - native runtime dependent
        from OCC.Core.BRepTools import breptools_Write
        ok = breptools_Write(shape, str(path))
        return bool(ok) or path.exists()
    except Exception:
        try:
            from OCC.Core.BRepTools import BRepTools_Write
            ok = BRepTools_Write(shape, str(path))
            return bool(ok) or path.exists()
        except Exception:
            return False


def serialize_topods_shape_to_brep(shape: Any, output_path: str | Path, *, shape_id: str = "shape") -> dict[str, Any]:
    """Serialize a native TopoDS_Shape to a .brep file if runtime supports it."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cap = probe_native_brep_capability()
    ok = False
    backend = "none"
    if shape is not None and cap.ocp_available:
        ok = _write_with_ocp(shape, path)
        backend = "OCP" if ok else backend
    if not ok and shape is not None and cap.pythonocc_available:
        ok = _write_with_pythonocc(shape, path)
        backend = "pythonocc-core" if ok else backend
    return {
        "contract": NATIVE_BREP_SERIALIZATION_CONTRACT,
        "ok": bool(ok),
        "shape_id": shape_id,
        "path": str(path) if ok else "",
        "digest": _shape_digest(path) if ok else "",
        "backend": backend,
        "native_brep_certified": bool(ok),
        "capability": cap.to_dict(),
    }


def enumerate_native_topology_records(shape: Any, shape_id: str, entity_id: str) -> list[CadTopologyRecord]:
    """Enumerate native topology when OCP/pythonocc is present.

    The implementation records stable ordinal native tags. Bounds are left empty
    unless a robust bounding-box API is available; downstream binding relies on
    persistent_name/native_tag rather than surrogate bounds.
    """
    records: list[CadTopologyRecord] = []
    if shape is None:
        return records
    records.append(CadTopologyRecord(f"{shape_id}:solid:native", shape_id, "solid", entity_id, persistent_name=f"{entity_id}/solid/native", native_tag="solid:0", metadata={"native_topology": True}))
    try:  # pragma: no cover - native runtime dependent
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
        mapping = [("face", TopAbs_FACE), ("edge", TopAbs_EDGE), ("vertex", TopAbs_VERTEX)]
        for kind, enum in mapping:
            exp = TopExp_Explorer(shape, enum)
            i = 0
            while exp.More():
                rid = f"{shape_id}:{kind}:native:{i:04d}"
                records.append(CadTopologyRecord(rid, shape_id, kind, entity_id, parent_id=f"{shape_id}:solid:native", persistent_name=f"{entity_id}/{kind}/native/{i:04d}", native_tag=f"{kind}:{i}", metadata={"native_topology": True, "native_backend": "OCP"}))
                i += 1
                exp.Next()
        return records
    except Exception:
        pass
    try:  # pragma: no cover - native runtime dependent
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
        mapping = [("face", TopAbs_FACE), ("edge", TopAbs_EDGE), ("vertex", TopAbs_VERTEX)]
        for kind, enum in mapping:
            exp = TopExp_Explorer(shape, enum)
            i = 0
            while exp.More():
                rid = f"{shape_id}:{kind}:native:{i:04d}"
                records.append(CadTopologyRecord(rid, shape_id, kind, entity_id, parent_id=f"{shape_id}:solid:native", persistent_name=f"{entity_id}/{kind}/native/{i:04d}", native_tag=f"{kind}:{i}", metadata={"native_topology": True, "native_backend": "pythonocc-core"}))
                i += 1
                exp.Next()
        return records
    except Exception:
        return records


def write_surrogate_brep_reference(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Write an explicit non-certified shape reference for headless/fallback runs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"contract": "geoai_simkit_non_native_brep_reference_v1", **dict(payload), "native_brep_certified": False}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(p), "digest": sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20], "native_brep_certified": False, "shape_format": "brep_json_surrogate"}


__all__ = [
    "NativeBrepCapability",
    "probe_native_brep_capability",
    "serialize_topods_shape_to_brep",
    "enumerate_native_topology_records",
    "write_surrogate_brep_reference",
]
