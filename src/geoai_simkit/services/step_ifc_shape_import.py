from __future__ import annotations

"""STEP/IFC solid topology import and CadShapeStore binding services.

The service is deliberately capability-aware.  When native runtimes such as
Gmsh/OCC, OCP/pythonocc or ifcopenshell are available, it records that native
binding is possible and uses the best available importer.  In minimal CI it can
still import deterministic topology references from STEP/IFC text and binds
those references to GeoProject/CadShapeStore without claiming native BRep
certification.
"""

from dataclasses import dataclass, field
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any, Iterable

from geoai_simkit._version import __version__
from geoai_simkit.services.native_brep_serialization import (
    probe_native_brep_capability,
    serialize_topods_shape_to_brep,
    enumerate_native_topology_records,
)
from geoai_simkit.geoproject.cad_shape_store import (
    CadEntityBinding,
    CadOperationHistoryRecord,
    CadSerializedShapeReference,
    CadShapeRecord,
    CadShapeStore,
    CadTopologyRecord,
    stable_ref_hash,
)
from geoai_simkit.geoproject.document import GeometryVolume

STEP_IFC_IMPORT_CONTRACT = "geoai_simkit_step_ifc_solid_topology_import_v1"
STEP_IFC_CAPABILITY_CONTRACT = "geoai_simkit_step_ifc_import_capability_v1"


def _optional_import(name: str) -> tuple[bool, str]:
    try:
        __import__(name)
        return True, ""
    except Exception as exc:  # pragma: no cover - host dependent
        return False, f"{type(exc).__name__}: {exc}"


@dataclass(slots=True)
class StepIfcImportCapability:
    contract: str = STEP_IFC_CAPABILITY_CONTRACT
    gmsh_available: bool = False
    gmsh_occ_import_shapes: bool = False
    ifcopenshell_available: bool = False
    ocp_available: bool = False
    pythonocc_available: bool = False
    native_step_possible: bool = False
    native_ifc_possible: bool = False
    native_brep_serialization_possible: bool = False
    native_topology_enumeration_possible: bool = False
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "gmsh_available": self.gmsh_available,
            "gmsh_occ_import_shapes": self.gmsh_occ_import_shapes,
            "ifcopenshell_available": self.ifcopenshell_available,
            "ocp_available": self.ocp_available,
            "pythonocc_available": self.pythonocc_available,
            "native_step_possible": self.native_step_possible,
            "native_ifc_possible": self.native_ifc_possible,
            "native_brep_serialization_possible": self.native_brep_serialization_possible,
            "native_topology_enumeration_possible": self.native_topology_enumeration_possible,
            "errors": dict(self.errors),
            "native_binding_policy": "native only when STEP/IFC runtime imports exact solids; surrogate imports are explicitly marked",
        }


@dataclass(slots=True)
class ImportedSolidRecord:
    id: str
    name: str
    source_format: str
    bounds: tuple[float, float, float, float, float, float]
    role: str = "imported_solid"
    material_id: str = ""
    native_shape_available: bool = False
    native_brep_certified: bool = False
    source_native_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source_format": self.source_format,
            "bounds": list(self.bounds),
            "role": self.role,
            "material_id": self.material_id,
            "native_shape_available": bool(self.native_shape_available),
            "native_brep_certified": bool(self.native_brep_certified),
            "source_native_id": self.source_native_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class StepIfcImportReport:
    contract: str = STEP_IFC_IMPORT_CONTRACT
    ok: bool = False
    status: str = "not_run"
    source_path: str = ""
    source_format: str = ""
    backend: str = ""
    native_backend_used: bool = False
    fallback_used: bool = True
    native_brep_certified: bool = False
    imported_solid_count: int = 0
    imported_volume_ids: list[str] = field(default_factory=list)
    shape_ids: list[str] = field(default_factory=list)
    topology_record_count: int = 0
    serialized_ref_count: int = 0
    reference_dir: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "status": self.status,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "backend": self.backend,
            "native_backend_used": bool(self.native_backend_used),
            "fallback_used": bool(self.fallback_used),
            "native_brep_certified": bool(self.native_brep_certified),
            "imported_solid_count": self.imported_solid_count,
            "imported_volume_ids": list(self.imported_volume_ids),
            "shape_ids": list(self.shape_ids),
            "topology_record_count": self.topology_record_count,
            "serialized_ref_count": self.serialized_ref_count,
            "reference_dir": self.reference_dir,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def probe_step_ifc_import_capability() -> StepIfcImportCapability:
    errors: dict[str, str] = {}
    gmsh_available, err = _optional_import("gmsh")
    gmsh_occ_import_shapes = False
    if gmsh_available:
        try:  # pragma: no cover - host dependent
            import gmsh  # type: ignore
            gmsh_occ_import_shapes = bool(hasattr(gmsh.model, "occ") and hasattr(gmsh.model.occ, "importShapes"))
        except Exception as exc:  # pragma: no cover
            errors["gmsh"] = f"{type(exc).__name__}: {exc}"
    elif err:
        errors["gmsh"] = err
    ifcopenshell_available, err = _optional_import("ifcopenshell")
    if err:
        errors["ifcopenshell"] = err
    ocp_available, err = _optional_import("OCP")
    if err:
        errors["OCP"] = err
    pythonocc_available, err = _optional_import("OCC.Core")
    if err:
        errors["OCC.Core"] = err
    brep_cap = probe_native_brep_capability()
    native_step_possible = bool(gmsh_occ_import_shapes or ocp_available or pythonocc_available)
    native_ifc_possible = bool(ifcopenshell_available)
    errors.update({f"native_brep.{k}": v for k, v in brep_cap.errors.items() if k not in errors})
    return StepIfcImportCapability(
        gmsh_available=gmsh_available,
        gmsh_occ_import_shapes=gmsh_occ_import_shapes,
        ifcopenshell_available=ifcopenshell_available,
        ocp_available=ocp_available,
        pythonocc_available=pythonocc_available,
        native_step_possible=native_step_possible,
        native_ifc_possible=native_ifc_possible,
        native_brep_serialization_possible=bool(brep_cap.native_brep_serialization_possible),
        native_topology_enumeration_possible=bool(brep_cap.native_topology_enumeration_possible),
        errors=errors,
    )


def _detect_format(path: Path, explicit: str | None = None) -> str:
    if explicit:
        text = explicit.lower().strip().lstrip(".")
        if text in {"step", "stp"}:
            return "step"
        if text == "ifc":
            return "ifc"
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"step", "stp"}:
        return "step"
    if suffix == "ifc":
        return "ifc"
    return suffix or "unknown"


def _safe_id(text: str, fallback: str = "solid") -> str:
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(text or ""))
    clean = "_".join(part for part in clean.split("_") if part)
    return clean or fallback


def _bounds_from_points(points: Iterable[Iterable[float]]) -> tuple[float, float, float, float, float, float] | None:
    pts = [tuple(float(v) for v in list(p)[:3]) for p in points]
    pts = [p for p in pts if len(p) == 3]
    if not pts:
        return None
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _normalize_bounds(bounds: Iterable[Any] | None) -> tuple[float, float, float, float, float, float]:
    vals = [float(v) for v in list(bounds or [])[:6]]
    while len(vals) < 6:
        vals.append(0.0)
    x0, x1, y0, y1, z0, z1 = vals[:6]
    return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1))


def _parse_embedded_geoai_solids(text: str, source_format: str) -> list[ImportedSolidRecord]:
    marker = "GEOAI_SIMKIT_SOLIDS"
    if marker not in text:
        return []
    records: list[ImportedSolidRecord] = []
    for line in text.splitlines():
        if marker not in line:
            continue
        payload_text = line.split(marker, 1)[1].lstrip(":= #/*-").strip()
        if payload_text.endswith("*/"):
            payload_text = payload_text[:-2].strip()
        if payload_text.startswith("{") and "}" in payload_text:
            payload_text = payload_text[: payload_text.rfind("}") + 1]
        elif payload_text.startswith("[") and "]" in payload_text:
            payload_text = payload_text[: payload_text.rfind("]") + 1]
        try:
            payload = json.loads(payload_text)
        except Exception:
            continue
        solids = payload.get("solids", payload if isinstance(payload, list) else [])
        for idx, row in enumerate(list(solids or []), start=1):
            row = dict(row or {})
            sid = _safe_id(str(row.get("id") or row.get("name") or f"{source_format}_solid_{idx}"), f"{source_format}_solid_{idx}")
            records.append(ImportedSolidRecord(
                id=sid,
                name=str(row.get("name") or sid),
                source_format=source_format,
                bounds=_normalize_bounds(row.get("bounds") or row.get("bbox") or [0, 1, 0, 1, 0, 1]),
                role=str(row.get("role") or "imported_solid"),
                material_id=str(row.get("material_id") or ""),
                source_native_id=str(row.get("native_id") or row.get("guid") or ""),
                metadata={"embedded_geoai_manifest": True, **dict(row.get("metadata", {}) or {})},
            ))
    return records


def _parse_step_ifc_points(text: str, source_format: str) -> list[ImportedSolidRecord]:
    nums = r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?"
    points: list[tuple[float, float, float]] = []
    if source_format == "step":
        # ISO-10303 CARTESIAN_POINT('',(x,y,z))
        pattern = re.compile(r"CARTESIAN_POINT\s*\([^\(]*\(\s*(%s)\s*,\s*(%s)\s*,\s*(%s)\s*\)" % (nums, nums, nums), re.I)
        points = [(float(a), float(b), float(c)) for a, b, c in pattern.findall(text)]
    elif source_format == "ifc":
        pattern = re.compile(r"IFCCARTESIANPOINT\s*\(\s*\(\s*(%s)\s*,\s*(%s)\s*,\s*(%s)\s*\)" % (nums, nums, nums), re.I)
        points = [(float(a), float(b), float(c)) for a, b, c in pattern.findall(text)]
    b = _bounds_from_points(points)
    if b is None:
        return []
    return [ImportedSolidRecord(id=f"{source_format}_solid_001", name=f"Imported {source_format.upper()} solid", source_format=source_format, bounds=b, metadata={"parsed_point_count": len(points), "surrogate_from_points": True})]



def _try_native_step_brep(path: Path, output_dir: Path, shape_id: str, entity_id: str) -> dict[str, Any]:
    """Best-effort native STEP -> TopoDS_Shape -> .brep serialization.

    Returns ok=False when OCP/pythonocc is absent or cannot read the file. It is
    deliberately isolated so fallback imports remain deterministic.
    """
    out = {"ok": False, "backend": "none", "native_shape": None, "serialization": {}, "topology_records": []}
    shape = None
    backend = "none"
    try:  # pragma: no cover - native runtime dependent
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status == IFSelect_RetDone:
            reader.TransferRoots()
            shape = reader.OneShape()
            backend = "OCP.STEPControl"
    except Exception:
        shape = None
    if shape is None:
        try:  # pragma: no cover - native runtime dependent
            from OCC.Core.STEPControl import STEPControl_Reader
            from OCC.Core.IFSelect import IFSelect_RetDone
            reader = STEPControl_Reader()
            status = reader.ReadFile(str(path))
            if status == IFSelect_RetDone:
                reader.TransferRoots()
                shape = reader.OneShape()
                backend = "OCC.Core.STEPControl"
        except Exception:
            shape = None
    if shape is None:
        return out
    brep_path = output_dir / "native_brep_refs" / f"{shape_id}.brep"
    serialization = serialize_topods_shape_to_brep(shape, brep_path, shape_id=shape_id)
    topo = enumerate_native_topology_records(shape, shape_id, entity_id)
    if serialization.get("ok") and topo:
        out.update({"ok": True, "backend": backend, "native_shape": shape, "serialization": serialization, "topology_records": topo})
    return out


def _extract_ifc_product_records(path: Path) -> list[ImportedSolidRecord]:
    """Best-effort IFC product extraction using ifcopenshell.

    This extracts product identity and, when geometry is available, a mesh bbox.
    It is exact at product identity level but not BRep-certified unless a native
    TopoDS serialization backend is added.
    """
    try:  # pragma: no cover - native runtime dependent
        import ifcopenshell  # type: ignore
        model = ifcopenshell.open(str(path))
    except Exception:
        return []
    records: list[ImportedSolidRecord] = []
    products = []
    for typ in ("IfcBuildingElement", "IfcElement", "IfcProduct"):
        try:
            products.extend(list(model.by_type(typ)))
        except Exception:
            pass
    seen: set[str] = set()
    for idx, product in enumerate(products, start=1):
        guid = str(getattr(product, "GlobalId", "") or f"ifc_product_{idx:03d}")
        if guid in seen:
            continue
        seen.add(guid)
        name = str(getattr(product, "Name", "") or guid)
        bounds = None
        try:  # pragma: no cover - native runtime dependent
            import ifcopenshell.geom  # type: ignore
            settings = ifcopenshell.geom.settings()
            shape = ifcopenshell.geom.create_shape(settings, product)
            verts = list(getattr(shape.geometry, "verts", []) or [])
            pts = [verts[i:i+3] for i in range(0, len(verts), 3)]
            bounds = _bounds_from_points(pts)
        except Exception:
            bounds = None
        records.append(ImportedSolidRecord(
            id=_safe_id(guid, f"ifc_product_{idx:03d}"),
            name=name,
            source_format="ifc",
            bounds=bounds or (0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
            role="ifc_product_solid",
            source_native_id=guid,
            native_shape_available=True,
            native_brep_certified=False,
            metadata={"ifc_product_guid": guid, "ifc_product_name": name, "ifcopenshell_product_extraction": True, "bbox_from_ifc_geometry": bool(bounds)},
        ))
    return records

def _fallback_records_from_file(path: Path, source_format: str) -> list[ImportedSolidRecord]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    records = _parse_embedded_geoai_solids(text, source_format)
    if records:
        return records
    records = _parse_step_ifc_points(text, source_format)
    if records:
        return records
    # Minimal deterministic placeholder for files without parseable geometry.
    stem = _safe_id(path.stem, f"{source_format}_solid")
    return [ImportedSolidRecord(id=stem, name=f"Imported {path.name}", source_format=source_format, bounds=(0.0, 1.0, 0.0, 1.0, 0.0, 1.0), metadata={"fallback_reason": "no_parseable_solid_geometry"})]


def _topology_for_shape(shape_id: str, entity_id: str, bounds: tuple[float, float, float, float, float, float], *, source_format: str) -> list[CadTopologyRecord]:
    x0, x1, y0, y1, z0, z1 = bounds
    records = [CadTopologyRecord(f"{shape_id}:solid", shape_id, "solid", entity_id, persistent_name=f"{entity_id}/solid", bounds=bounds, metadata={"import_format": source_format})]
    faces = [
        ("xmin", (x0, x0, y0, y1, z0, z1), "-X"), ("xmax", (x1, x1, y0, y1, z0, z1), "+X"),
        ("ymin", (x0, x1, y0, y0, z0, z1), "-Y"), ("ymax", (x0, x1, y1, y1, z0, z1), "+Y"),
        ("zmin", (x0, x1, y0, y1, z0, z0), "-Z"), ("zmax", (x0, x1, y0, y1, z1, z1), "+Z"),
    ]
    for name, b, normal in faces:
        records.append(CadTopologyRecord(f"{shape_id}:face:{name}", shape_id, "face", entity_id, parent_id=f"{shape_id}:solid", persistent_name=f"{entity_id}/face/{name}", bounds=b, orientation=normal, metadata={"import_format": source_format, "normal": normal}))
    edge_bounds = [
        ((x0, x1, y0, y0, z0, z0), "x_ymin_zmin"), ((x0, x1, y1, y1, z0, z0), "x_ymax_zmin"),
        ((x0, x1, y0, y0, z1, z1), "x_ymin_zmax"), ((x0, x1, y1, y1, z1, z1), "x_ymax_zmax"),
        ((x0, x0, y0, y1, z0, z0), "y_xmin_zmin"), ((x1, x1, y0, y1, z0, z0), "y_xmax_zmin"),
        ((x0, x0, y0, y1, z1, z1), "y_xmin_zmax"), ((x1, x1, y0, y1, z1, z1), "y_xmax_zmax"),
        ((x0, x0, y0, y0, z0, z1), "z_xmin_ymin"), ((x1, x1, y0, y0, z0, z1), "z_xmax_ymin"),
        ((x0, x0, y1, y1, z0, z1), "z_xmin_ymax"), ((x1, x1, y1, y1, z0, z1), "z_xmax_ymax"),
    ]
    for i, (b, name) in enumerate(edge_bounds):
        records.append(CadTopologyRecord(f"{shape_id}:edge:{i:02d}", shape_id, "edge", entity_id, parent_id=f"{shape_id}:solid", persistent_name=f"{entity_id}/edge/{name}", bounds=b, orientation=name, metadata={"import_format": source_format, "edge_role": name}))
    vertex_points = [
        (x0, y0, z0), (x1, y0, z0), (x0, y1, z0), (x1, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x0, y1, z1), (x1, y1, z1),
    ]
    for i, (x, y, z) in enumerate(vertex_points):
        b = (x, x, y, y, z, z)
        records.append(CadTopologyRecord(f"{shape_id}:vertex:{i:02d}", shape_id, "vertex", entity_id, parent_id=f"{shape_id}:solid", persistent_name=f"{entity_id}/vertex/{i:02d}", bounds=b, metadata={"import_format": source_format, "vertex_index": i}))
    return records


def _ensure_store(project: Any) -> CadShapeStore:
    store = getattr(project, "cad_shape_store", None)
    if store is None or not isinstance(store, CadShapeStore):
        store = CadShapeStore(metadata={"created_by": "import_step_ifc_solid_topology"})
        project.cad_shape_store = store
    return store


def _write_ref_payload(path: Path, payload: dict[str, Any]) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    return str(path), digest


def import_step_ifc_solid_topology(
    project: Any,
    source_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    source_format: str | None = None,
    attach: bool = True,
    require_native: bool = False,
    export_references: bool = True,
) -> StepIfcImportReport:
    path = Path(source_path)
    fmt = _detect_format(path, source_format)
    cap = probe_step_ifc_import_capability()
    warnings: list[str] = []
    if not path.exists():
        return StepIfcImportReport(ok=False, status="source_not_found", source_path=str(path), source_format=fmt, backend="none", warnings=[f"Source file not found: {path}"], metadata={"capability": cap.to_dict()})
    native_possible = bool((fmt == "step" and cap.native_step_possible) or (fmt == "ifc" and cap.native_ifc_possible))
    if require_native and not native_possible:
        return StepIfcImportReport(ok=False, status="native_import_unavailable", source_path=str(path), source_format=fmt, backend="none", native_backend_used=False, fallback_used=False, warnings=["Native STEP/IFC solid import was required but runtime is unavailable."], metadata={"capability": cap.to_dict()})

    # Native IFC product extraction is identity-exact when ifcopenshell is available,
    # but still not BRep-certified unless a TopoDS/BRep serializer is available.
    native_product_records = _extract_ifc_product_records(path) if fmt == "ifc" and cap.ifcopenshell_available else []
    records = native_product_records or _fallback_records_from_file(path, fmt)
    backend = f"{fmt}_topology_surrogate"
    native_backend_used = False
    fallback_used = True
    if native_product_records:
        backend = "ifc_product_exact_solid_extraction"
        native_backend_used = True
        fallback_used = False
        warnings.append("IFC product identities were extracted with ifcopenshell; BRep certification remains false unless native TopoDS serialization succeeds.")
    elif native_possible:
        warnings.append("Native STEP/IFC runtime detected; importer will attempt STEP BRep serialization where possible and otherwise records binding references with certification false.")
        backend = f"{fmt}_native_runtime_detected_binding_surrogate"
    else:
        warnings.append(f"Native {fmt.upper()} importer unavailable; imported explicit {fmt.upper()} topology surrogate and bound it to CadShapeStore.")

    store = _ensure_store(project)
    root = Path(output_dir) if output_dir is not None else Path("exports/step_ifc_import")
    ref_dir = root / "cad_import_refs"
    if export_references:
        ref_dir.mkdir(parents=True, exist_ok=True)

    imported_volume_ids: list[str] = []
    shape_ids: list[str] = []
    source_digest = sha1(path.read_bytes()).hexdigest()[:20]
    for idx, rec in enumerate(records, start=1):
        entity_id = _safe_id(f"imported_{fmt}_{rec.id}", f"imported_{fmt}_{idx:03d}")
        # Avoid clobbering existing volumes.
        base_entity_id = entity_id
        k = 2
        while entity_id in getattr(project.geometry_model, "volumes", {}):
            entity_id = f"{base_entity_id}_{k}"
            k += 1
        shape_id = f"shape_{entity_id}"
        ref_id = f"ref_{shape_id}"
        topology = _topology_for_shape(shape_id, entity_id, rec.bounds, source_format=fmt)
        native_brep_info: dict[str, Any] = {}
        if fmt == "step" and cap.native_brep_serialization_possible:
            native_brep_info = _try_native_step_brep(path, root, shape_id, entity_id)
            if native_brep_info.get("ok"):
                topology = list(native_brep_info.get("topology_records") or topology)
                backend = str(native_brep_info.get("backend") or backend)
                native_backend_used = True
                fallback_used = False
        volume = GeometryVolume(
            id=entity_id,
            name=rec.name,
            bounds=rec.bounds,
            role=rec.role,
            material_id=rec.material_id or None,
            metadata={
                "source": "step_ifc_solid_topology_import",
                "source_path": str(path),
                "source_format": fmt,
                "source_native_id": rec.source_native_id,
                "shape_id": shape_id,
                "native_shape_available": bool(native_backend_used),
                "native_brep_certified": bool(native_brep_info.get("ok", False)),
                **dict(rec.metadata),
            },
        )
        if attach:
            project.geometry_model.volumes[entity_id] = volume
        payload = {
            "contract": "geoai_simkit_imported_step_ifc_shape_reference_v1",
            "source_path": str(path),
            "source_format": fmt,
            "source_digest": source_digest,
            "source_native_id": rec.source_native_id,
            "entity_id": entity_id,
            "shape_id": shape_id,
            "bounds": list(rec.bounds),
            "native_brep_certified": bool(native_brep_info.get("ok", False)),
            "backend": backend,
            "record": rec.to_dict(),
        }
        if native_brep_info.get("ok") and native_brep_info.get("serialization", {}).get("path"):
            ref_path = str(native_brep_info["serialization"].get("path"))
            digest = str(native_brep_info["serialization"].get("digest", ""))
            storage = "external_file"
            ref_payload = {"digest": digest, "source_path": str(path), "entity_id": entity_id, "shape_id": shape_id, "native_brep": True}
            shape_format_value = "brep"
        elif export_references:
            ref_path, digest = _write_ref_payload(ref_dir / f"{shape_id}.{fmt}.shape.json", payload)
            storage = "external_file"
            ref_payload = {"digest": digest, "source_path": str(path), "entity_id": entity_id, "shape_id": shape_id}
            shape_format_value = fmt
        else:
            digest = stable_ref_hash(payload)
            ref_path = ""
            storage = "inline"
            ref_payload = payload
            shape_format_value = fmt
        store.serialized_refs[ref_id] = CadSerializedShapeReference(
            id=ref_id,
            backend="step_ifc_import",
            shape_format=shape_format_value,
            storage=storage,
            path=ref_path,
            digest=digest,
            payload=ref_payload,
            metadata={"source_digest": source_digest, "native_brep_certified": bool(native_brep_info.get("ok", False)), "backend": backend, "native_serialization": dict(native_brep_info.get("serialization", {}) or {})},
        )
        for topo in topology:
            store.topology_records[topo.id] = topo
        store.shapes[shape_id] = CadShapeRecord(
            id=shape_id,
            name=rec.name,
            kind="solid",
            source_entity_ids=[entity_id],
            serialized_ref_id=ref_id,
            backend="step_ifc_import",
            native_shape_available=bool(native_backend_used),
            brep_serialized=True,
            topology_ids=[t.id for t in topology],
            material_id=rec.material_id,
            phase_ids=[],
            metadata={"source_format": fmt, "source_path": str(path), "native_brep_certified": bool(native_brep_info.get("ok", False)), "backend": backend, "bounds": list(rec.bounds), "native_serialization": dict(native_brep_info.get("serialization", {}) or {})},
        )
        store.entity_bindings[f"binding_{entity_id}"] = CadEntityBinding(
            id=f"binding_{entity_id}",
            entity_id=entity_id,
            entity_type="volume",
            shape_id=shape_id,
            topology_ids=[t.id for t in topology],
            binding_role="imported_solid_shape_binding",
            material_id=rec.material_id,
            phase_ids=[],
            metadata={"source_format": fmt, "source_path": str(path), "native_brep_certified": bool(native_brep_info.get("ok", False))},
        )
        imported_volume_ids.append(entity_id)
        shape_ids.append(shape_id)

    op_id = f"operation_import_{fmt}_{len(store.operation_history)+1:03d}"
    store.operation_history[op_id] = CadOperationHistoryRecord(
        id=op_id,
        operation=f"import_{fmt}_solid_topology",
        input_shape_ids=[],
        output_shape_ids=shape_ids,
        input_entity_ids=[],
        output_entity_ids=imported_volume_ids,
        backend=backend,
        native_backend_used=native_backend_used,
        fallback_used=fallback_used,
        status="imported",
        metadata={"source_path": str(path), "source_format": fmt, "capability": cap.to_dict()},
    )
    store.metadata["last_step_ifc_import"] = {"source_path": str(path), "source_format": fmt, "shape_ids": shape_ids, "native_brep_certified": False}
    store.metadata["summary"] = store.summary()
    if attach:
        project.cad_shape_store = store
        project.metadata["release_1_4_3_step_ifc_import"] = {
            "source_path": str(path),
            "source_format": fmt,
            "backend": backend,
            "native_backend_used": native_backend_used,
            "fallback_used": fallback_used,
            "native_brep_certified": False,
            "imported_volume_ids": imported_volume_ids,
            "shape_ids": shape_ids,
        }
        if hasattr(project, "mark_changed"):
            project.mark_changed(["geometry", "topology", "cad_shape_store", "mesh", "solver", "result"], action="import_step_ifc_solid_topology", affected_entities=imported_volume_ids)
    status = "step_ifc_solid_topology_bound" if imported_volume_ids else "no_solids_imported"
    return StepIfcImportReport(
        ok=bool(imported_volume_ids),
        status=status,
        source_path=str(path),
        source_format=fmt,
        backend=backend,
        native_backend_used=native_backend_used,
        fallback_used=fallback_used,
        native_brep_certified=False,
        imported_solid_count=len(imported_volume_ids),
        imported_volume_ids=imported_volume_ids,
        shape_ids=shape_ids,
        topology_record_count=sum(len(store.shapes[sid].topology_ids) for sid in shape_ids if sid in store.shapes),
        serialized_ref_count=len(shape_ids),
        reference_dir=str(ref_dir) if export_references else "",
        warnings=warnings,
        metadata={"capability": cap.to_dict(), "cad_shape_store_summary": store.summary()},
    )


def validate_step_ifc_shape_bindings(project: Any) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    store = getattr(project, "cad_shape_store", None)
    if store is None:
        return {"contract": "geoai_simkit_step_ifc_shape_binding_validation_v1", "ok": False, "blockers": ["CadShapeStore is missing."], "warnings": []}
    imported_shapes = [s for s in store.shapes.values() if s.backend == "step_ifc_import" or s.metadata.get("source_format") in {"step", "ifc"}]
    if not imported_shapes:
        blockers.append("No STEP/IFC imported shapes are bound in CadShapeStore.")
    for shape in imported_shapes:
        if shape.serialized_ref_id not in store.serialized_refs:
            blockers.append(f"Imported shape {shape.id} is missing serialized reference {shape.serialized_ref_id}.")
        if not shape.topology_ids:
            blockers.append(f"Imported shape {shape.id} has no topology records.")
        missing = [tid for tid in shape.topology_ids if tid not in store.topology_records]
        if missing:
            blockers.append(f"Imported shape {shape.id} references missing topology records: {missing[:3]}.")
        if not any(b.shape_id == shape.id for b in store.entity_bindings.values()):
            blockers.append(f"Imported shape {shape.id} has no GeoProject entity binding.")
    if imported_shapes and not any(s.native_shape_available for s in imported_shapes):
        warnings.append("STEP/IFC shapes are imported as serialized topology references; native BRep certification is false in this run.")
    return {
        "contract": "geoai_simkit_step_ifc_shape_binding_validation_v1",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "imported_shape_count": len(imported_shapes),
        "imported_volume_ids": [sid for s in imported_shapes for sid in s.source_entity_ids],
        "summary": store.summary(),
    }


__all__ = [
    "StepIfcImportCapability",
    "StepIfcImportReport",
    "ImportedSolidRecord",
    "probe_step_ifc_import_capability",
    "import_step_ifc_solid_topology",
    "validate_step_ifc_shape_bindings",
]
