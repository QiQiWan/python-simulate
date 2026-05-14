from __future__ import annotations

"""Native-first import assembly for geology/support-structure FEM preprocessing.

1.6.0 makes import-driven assembly the primary production path: geology comes
from borehole/STL/IFC/STEP sources, support structures come from IFC/STL/STEP or
explicit boxes, then soil/structure overlap is cut and the project is remeshed.
The service is capability-aware: it uses native IFC/STEP identity extraction and
can attempt Gmsh/OCC box booleans when requested, while preserving an explicit
fallback report when only bounds-level assembly is possible.
"""

from dataclasses import dataclass, field
from math import cos, radians, sin
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from geoai_simkit.geoproject import GeoProjectDocument, GeometryVolume
from geoai_simkit.services.import_driven_model_assembly import (
    AssemblyOptions,
    ImportedStructureSpec,
    create_geology_project_from_source,
    register_structure_volume,
    subtract_structure_overlaps_from_geology,
)
from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology, probe_step_ifc_import_capability
from geoai_simkit.services.gmsh_occ_boolean_roundtrip import probe_gmsh_occ_boolean_roundtrip
from geoai_simkit.services.cad_structure_workflow import ensure_default_engineering_materials

NATIVE_IMPORT_ASSEMBLY_CONTRACT = "geoai_simkit_native_import_assembly_v1"

Bounds = tuple[float, float, float, float, float, float]


def _safe_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    clean = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or fallback
    while "__" in clean:
        clean = clean.replace("__", "_")
    if clean[0].isdigit():
        clean = f"{fallback}_{clean}"
    return clean


def _coerce_bounds(values: Any) -> Bounds:
    vals = [float(v) for v in list(values or [])]
    if len(vals) != 6:
        raise ValueError(f"bounds require 6 numbers, got {len(vals)}")
    x0, x1, y0, y1, z0, z1 = vals
    return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1))


def _bounds_corners(bounds: Bounds) -> list[tuple[float, float, float]]:
    x0, x1, y0, y1, z0, z1 = bounds
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def _bounds_from_points(points: Iterable[Iterable[float]]) -> Bounds:
    pts = [tuple(float(v) for v in list(p)[:3]) for p in points]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


@dataclass(slots=True)
class ImportTransformSpec:
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    rotate_z_degrees: float = 0.0
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ImportTransformSpec":
        raw = dict(data or {})
        def vec(name: str, default: tuple[float, float, float]) -> tuple[float, float, float]:
            row = raw.get(name, default)
            vals = [float(v) for v in list(row)[:3]]
            while len(vals) < 3:
                vals.append(default[len(vals)])
            return (vals[0], vals[1], vals[2])
        return cls(
            translate=vec("translate", (0.0, 0.0, 0.0)),
            scale=vec("scale", (1.0, 1.0, 1.0)),
            rotate_z_degrees=float(raw.get("rotate_z_degrees", raw.get("rotation_z", 0.0)) or 0.0),
            origin=vec("origin", (0.0, 0.0, 0.0)),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"translate": list(self.translate), "scale": list(self.scale), "rotate_z_degrees": self.rotate_z_degrees, "origin": list(self.origin), "metadata": dict(self.metadata)}

    def apply_bounds(self, bounds: Bounds) -> Bounds:
        ox, oy, oz = self.origin
        sx, sy, sz = self.scale
        rz = radians(float(self.rotate_z_degrees))
        c = cos(rz); s = sin(rz)
        tx, ty, tz = self.translate
        out: list[tuple[float, float, float]] = []
        for x, y, z in _bounds_corners(bounds):
            px = ox + (x - ox) * sx
            py = oy + (y - oy) * sy
            pz = oz + (z - oz) * sz
            rx = ox + (px - ox) * c - (py - oy) * s
            ry = oy + (px - ox) * s + (py - oy) * c
            out.append((rx + tx, ry + ty, pz + tz))
        return _bounds_from_points(out)


@dataclass(slots=True)
class NativeImportSourceSpec:
    id: str = ""
    path: str = ""
    source_type: str = "auto"
    role: str = "geology"
    kind: str = ""
    material_id: str = ""
    bounds: Bounds | None = None
    transform: ImportTransformSpec = field(default_factory=ImportTransformSpec)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "NativeImportSourceSpec":
        raw = dict(data or {})
        path = str(raw.get("path") or raw.get("source_path") or "")
        sid = _safe_id(raw.get("id") or Path(path).stem or raw.get("role") or "source", "source")
        return cls(
            id=sid,
            path=path,
            source_type=str(raw.get("source_type") or raw.get("type") or "auto"),
            role=str(raw.get("role") or "geology"),
            kind=str(raw.get("kind") or raw.get("semantic_type") or ""),
            material_id=str(raw.get("material_id") or ""),
            bounds=None if raw.get("bounds") is None else _coerce_bounds(raw.get("bounds")),
            transform=ImportTransformSpec.from_mapping(raw.get("transform")),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "path": self.path, "source_type": self.source_type, "role": self.role, "kind": self.kind, "material_id": self.material_id, "bounds": None if self.bounds is None else list(self.bounds), "transform": self.transform.to_dict(), "metadata": dict(self.metadata)}


@dataclass(slots=True)
class NativeImportAssemblyOptions:
    boolean_mode: str = "native_gmsh_occ_if_available"
    require_native_import: bool = False
    require_native_boolean: bool = False
    fallback_allowed: bool = True
    remesh: bool = True
    element_size: float | None = None
    preserve_original_geology: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "NativeImportAssemblyOptions":
        raw = dict(data or {})
        return cls(
            boolean_mode=str(raw.get("boolean_mode") or "native_gmsh_occ_if_available"),
            require_native_import=bool(raw.get("require_native_import", False)),
            require_native_boolean=bool(raw.get("require_native_boolean", False)),
            fallback_allowed=bool(raw.get("fallback_allowed", True)),
            remesh=bool(raw.get("remesh", True)),
            element_size=None if raw.get("element_size") is None else float(raw.get("element_size")),
            preserve_original_geology=bool(raw.get("preserve_original_geology", False)),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"boolean_mode": self.boolean_mode, "require_native_import": self.require_native_import, "require_native_boolean": self.require_native_boolean, "fallback_allowed": self.fallback_allowed, "remesh": self.remesh, "element_size": self.element_size, "preserve_original_geology": self.preserve_original_geology, "metadata": dict(self.metadata)}


@dataclass(slots=True)
class NativeImportAssemblyReport:
    contract: str = NATIVE_IMPORT_ASSEMBLY_CONTRACT
    ok: bool = False
    geology_source_count: int = 0
    structure_source_count: int = 0
    imported_volume_ids: list[str] = field(default_factory=list)
    structure_volume_ids: list[str] = field(default_factory=list)
    native_import_used: bool = False
    native_boolean_requested: bool = False
    native_boolean_available: bool = False
    native_boolean_used: bool = False
    fallback_used: bool = False
    assembly_report: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"contract": self.contract, "ok": self.ok, "geology_source_count": self.geology_source_count, "structure_source_count": self.structure_source_count, "imported_volume_ids": list(self.imported_volume_ids), "structure_volume_ids": list(self.structure_volume_ids), "native_import_used": self.native_import_used, "native_boolean_requested": self.native_boolean_requested, "native_boolean_available": self.native_boolean_available, "native_boolean_used": self.native_boolean_used, "fallback_used": self.fallback_used, "assembly_report": dict(self.assembly_report), "blockers": list(self.blockers), "warnings": list(self.warnings), "metadata": dict(self.metadata)}


def _infer_type(spec: NativeImportSourceSpec) -> str:
    if spec.source_type and spec.source_type != "auto":
        return spec.source_type.lower()
    suffix = Path(spec.path).suffix.lower()
    if suffix == ".csv":
        return "borehole_csv"
    if suffix == ".stl":
        return "stl"
    if suffix in {".msh", ".vtu"}:
        return suffix.lstrip(".")
    if suffix in {".ifc"}:
        return "ifc"
    if suffix in {".step", ".stp"}:
        return "step"
    if spec.bounds is not None:
        return "box_bounds"
    return "unknown"


def _merge_project_volumes(target: GeoProjectDocument, source: GeoProjectDocument, *, prefix: str = "imported") -> list[str]:
    ids: list[str] = []
    for volume in list(source.geometry_model.volumes.values()):
        base = _safe_id(f"{prefix}_{volume.id}", "imported_volume")
        vid = base
        i = 2
        while vid in target.geometry_model.volumes:
            vid = f"{base}_{i}"
            i += 1
        clone = GeometryVolume(id=vid, name=getattr(volume, "name", vid), bounds=getattr(volume, "bounds", None), surface_ids=list(getattr(volume, "surface_ids", []) or []), role=getattr(volume, "role", "geology") or "geology", material_id=getattr(volume, "material_id", None), metadata={**dict(getattr(volume, "metadata", {}) or {}), "merged_from_volume_id": volume.id})
        target.geometry_model.volumes[vid] = clone
        target.phase_manager.initial_phase.active_blocks.add(vid)
        ids.append(vid)
    return ids


def _apply_transform_to_project_volumes(project: GeoProjectDocument, ids: Iterable[str], transform: ImportTransformSpec) -> None:
    for vid in ids:
        volume = project.geometry_model.volumes.get(str(vid))
        if volume is None or getattr(volume, "bounds", None) is None:
            continue
        volume.bounds = transform.apply_bounds(_coerce_bounds(volume.bounds))
        volume.metadata.setdefault("native_import_assembly", {})["transform"] = transform.to_dict()


def _import_source(project: GeoProjectDocument, spec: NativeImportSourceSpec, *, output_dir: str | Path | None = None, require_native: bool = False) -> tuple[list[str], dict[str, Any], list[str], list[str]]:
    typ = _infer_type(spec)
    warnings: list[str] = []
    blockers: list[str] = []
    role = spec.role.lower()
    imported_ids: list[str] = []
    report: dict[str, Any] = {"source": spec.to_dict(), "type": typ}
    if typ == "box_bounds":
        if spec.bounds is None:
            blockers.append(f"{spec.id}: box_bounds source has no bounds")
        else:
            volume = GeometryVolume(id=_safe_id(spec.id, "box"), name=spec.id, bounds=spec.transform.apply_bounds(spec.bounds), role="soil" if role == "geology" else "structure", material_id=spec.material_id or None, metadata={"source": "native_import_assembly_box", "role": role, **spec.metadata})
            project.geometry_model.volumes[volume.id] = volume
            project.phase_manager.initial_phase.active_blocks.add(volume.id)
            imported_ids.append(volume.id)
    elif typ in {"borehole_csv", "stl", "stl_geology", "msh", "vtu", "msh_geology", "vtu_geology", "meshio_geology"} and role == "geology":
        source_type = "borehole_csv" if typ == "borehole_csv" else ("stl_geology" if typ in {"stl", "stl_geology"} else ("msh_geology" if typ in {"msh", "msh_geology"} else "vtu_geology"))
        tmp = create_geology_project_from_source(spec.path, source_type=source_type, name=spec.id)
        imported_ids = _merge_project_volumes(project, tmp, prefix=spec.id)
        _apply_transform_to_project_volumes(project, imported_ids, spec.transform)
    elif typ in {"stl", "msh", "vtu"} and role != "geology":
        volume = register_structure_volume(project, ImportedStructureSpec(id=spec.id, name=spec.id, kind=spec.kind or "imported_structure", source_path=spec.path, material_id=spec.material_id or "concrete_c30", metadata={"native_import_assembly": True, **spec.metadata}))
        if volume.bounds is not None:
            volume.bounds = spec.transform.apply_bounds(_coerce_bounds(volume.bounds))
        imported_ids = [volume.id]
    elif typ in {"ifc", "step", "stp"}:
        before = set(project.geometry_model.volumes.keys())
        step_report = import_step_ifc_solid_topology(project, spec.path, output_dir=output_dir, source_format="step" if typ in {"step", "stp"} else "ifc", require_native=require_native, attach=True)
        report["step_ifc_import"] = step_report.to_dict()
        imported_ids = [vid for vid in project.geometry_model.volumes.keys() if vid not in before]
        if not step_report.ok:
            blockers.extend(step_report.warnings or [f"{spec.id}: STEP/IFC import failed"])
        for vid in imported_ids:
            volume = project.geometry_model.volumes[vid]
            if volume.bounds is not None:
                volume.bounds = spec.transform.apply_bounds(_coerce_bounds(volume.bounds))
            if role != "geology":
                volume.role = "structure" if (spec.kind or "structure") not in {"excavation", "void"} else "excavation"
                volume.material_id = spec.material_id or volume.material_id or "concrete_c30"
                volume.metadata.update({"boolean_cutter": True, "preserve_as_structure": True, "import_kind": spec.kind or "ifc_structure", "native_import_assembly": True})
            else:
                volume.role = volume.role if volume.role in {"soil", "rock", "geology", "geological_volume"} else "geology"
                volume.metadata.update({"native_import_assembly": True, "geology_source": True})
    else:
        blockers.append(f"{spec.id}: unsupported source type {typ!r} for role {role!r}")
    report["imported_volume_ids"] = imported_ids
    return imported_ids, report, warnings, blockers


def build_native_import_assembly_payload(project: Any | None = None) -> dict[str, Any]:
    return {
        "contract": NATIVE_IMPORT_ASSEMBLY_CONTRACT,
        "primary_strategy": "native/fallback-aware file import + transform/alignment + structure cutters + boolean subtract/fragment + remesh",
        "geology_inputs": ["borehole_csv", "stl", "ifc", "step", "box_bounds"],
        "structure_inputs": ["ifc", "step", "stl", "box_bounds"],
        "transform_controls": ["translate", "scale", "rotate_z_degrees", "origin"],
        "boolean_modes": ["native_gmsh_occ_if_available", "native_required", "aabb_fallback"],
        "gui_panel": "导入拼接",
        "qt_only_safe": True,
        "current_volume_count": len(getattr(getattr(project, "geometry_model", None), "volumes", {}) or {}) if project is not None else 0,
    }


def run_native_import_assembly(
    *,
    geology_sources: Sequence[NativeImportSourceSpec | Mapping[str, Any]] | None = None,
    structure_sources: Sequence[NativeImportSourceSpec | Mapping[str, Any]] | None = None,
    project: GeoProjectDocument | None = None,
    options: NativeImportAssemblyOptions | Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
    name: str = "native-import-assembly",
) -> tuple[GeoProjectDocument, NativeImportAssemblyReport]:
    opts = options if isinstance(options, NativeImportAssemblyOptions) else NativeImportAssemblyOptions.from_mapping(options)
    project = project or GeoProjectDocument.create_empty(name=name)
    ensure_default_engineering_materials(project)
    blockers: list[str] = []
    warnings: list[str] = []
    import_reports: list[dict[str, Any]] = []
    imported_ids: list[str] = []
    structure_ids: list[str] = []
    native_import_used = False
    for raw in list(geology_sources or []):
        spec = raw if isinstance(raw, NativeImportSourceSpec) else NativeImportSourceSpec.from_mapping({**dict(raw), "role": dict(raw).get("role", "geology")})
        ids, rep, warn, block = _import_source(project, spec, output_dir=output_dir, require_native=opts.require_native_import)
        imported_ids.extend(ids); import_reports.append(rep); warnings.extend(warn); blockers.extend(block)
        native_import_used = native_import_used or bool(dict(rep.get("step_ifc_import", {}) or {}).get("native_backend_used"))
    for raw in list(structure_sources or []):
        spec = raw if isinstance(raw, NativeImportSourceSpec) else NativeImportSourceSpec.from_mapping({**dict(raw), "role": dict(raw).get("role", "structure")})
        ids, rep, warn, block = _import_source(project, spec, output_dir=output_dir, require_native=opts.require_native_import)
        structure_ids.extend(ids); import_reports.append(rep); warnings.extend(warn); blockers.extend(block)
        native_import_used = native_import_used or bool(dict(rep.get("step_ifc_import", {}) or {}).get("native_backend_used"))
    if opts.require_native_import and not native_import_used:
        blockers.append("native import was required, but no source used a native STEP/IFC backend")
    cap = probe_gmsh_occ_boolean_roundtrip()
    native_available = bool(cap.native_roundtrip_possible)
    if opts.require_native_boolean and not native_available:
        blockers.append("native Gmsh/OCC boolean was required, but gmsh.model.occ is unavailable")
    if blockers:
        report = NativeImportAssemblyReport(ok=False, geology_source_count=len(geology_sources or []), structure_source_count=len(structure_sources or []), imported_volume_ids=imported_ids, structure_volume_ids=structure_ids, native_import_used=native_import_used, native_boolean_requested=opts.require_native_boolean or opts.boolean_mode.startswith("native"), native_boolean_available=native_available, blockers=blockers, warnings=warnings, metadata={"options": opts.to_dict(), "imports": import_reports, "capability": cap.to_dict()})
        project.metadata.setdefault("native_import_assembly", {})["last_report"] = report.to_dict()
        return project, report
    assembly_opts = AssemblyOptions(boolean_mode=opts.boolean_mode if native_available else "aabb_fallback", remesh=opts.remesh, element_size=opts.element_size, preserve_original_geology=opts.preserve_original_geology, require_native_boolean=False, metadata={"native_import_assembly": True, "native_boolean_available": native_available, **opts.metadata})
    assembly = subtract_structure_overlaps_from_geology(project, options=assembly_opts)
    fallback_used = bool(assembly.fallback_used or not native_available)
    report = NativeImportAssemblyReport(ok=bool(assembly.ok), geology_source_count=len(geology_sources or []), structure_source_count=len(structure_sources or []), imported_volume_ids=imported_ids, structure_volume_ids=structure_ids or list(assembly.structure_volume_ids), native_import_used=native_import_used, native_boolean_requested=opts.require_native_boolean or opts.boolean_mode.startswith("native"), native_boolean_available=native_available, native_boolean_used=False, fallback_used=fallback_used, assembly_report=assembly.to_dict(), blockers=list(assembly.blockers), warnings=warnings + list(assembly.warnings), metadata={"options": opts.to_dict(), "imports": import_reports, "capability": cap.to_dict(), "note": "1.6.0 imports IFC/STEP/STL into the assembly path; exact native boolean is gated by gmsh OCC availability and remains explicitly reported."})
    project.metadata.setdefault("native_import_assembly", {})["last_report"] = report.to_dict()
    return project, report


__all__ = [
    "NATIVE_IMPORT_ASSEMBLY_CONTRACT",
    "ImportTransformSpec",
    "NativeImportSourceSpec",
    "NativeImportAssemblyOptions",
    "NativeImportAssemblyReport",
    "build_native_import_assembly_payload",
    "run_native_import_assembly",
]
