from __future__ import annotations

"""Import-driven geology/structure assembly workflow.

This module is the practical fallback route for desktop environments where
mouse CAD authoring is not yet reliable enough for production use.  It treats
STL/IFC/borehole imports as the primary geometry source, adds imported support
structures, subtracts structure volumes from geology volumes using either a
native backend in the future or a deterministic AABB fallback today, then
regenerates a physical-tagged Tet4 mesh.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from geoai_simkit.geoproject import GeoProjectDocument, GeometryVolume, MaterialRecord, StructureRecord
from geoai_simkit.modules import geology_import
from geoai_simkit.services.cad_fem_preprocessor import build_cad_fem_preprocessor, validate_cad_fem_preprocessor
from geoai_simkit.services.cad_structure_workflow import ensure_default_engineering_materials, auto_assign_materials_by_recognized_strata_and_structures
from geoai_simkit.services.gmsh_occ_project_mesher import generate_geoproject_gmsh_occ_tet4_mesh

IMPORT_DRIVEN_ASSEMBLY_CONTRACT = "geoai_simkit_import_driven_geology_structure_assembly_v1"

Bounds = tuple[float, float, float, float, float, float]


def _safe_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    out = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or fallback
    while "__" in out:
        out = out.replace("__", "_")
    if out[0].isdigit():
        out = f"{fallback}_{out}"
    return out


def _coerce_bounds(values: Any) -> Bounds:
    if values is None:
        raise ValueError("bounds are required")
    vals = [float(v) for v in list(values)]
    if len(vals) != 6:
        raise ValueError(f"bounds must contain 6 numbers, got {len(vals)}")
    xmin, xmax, ymin, ymax, zmin, zmax = vals
    if xmin > xmax:
        xmin, xmax = xmax, xmin
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    if zmin > zmax:
        zmin, zmax = zmax, zmin
    return (xmin, xmax, ymin, ymax, zmin, zmax)


def _volume(bounds: Bounds) -> float:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    return max(xmax - xmin, 0.0) * max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0)


def _intersection(a: Bounds, b: Bounds, *, tolerance: float = 1.0e-9) -> Bounds | None:
    xmin = max(a[0], b[0])
    xmax = min(a[1], b[1])
    ymin = max(a[2], b[2])
    ymax = min(a[3], b[3])
    zmin = max(a[4], b[4])
    zmax = min(a[5], b[5])
    if xmax - xmin <= tolerance or ymax - ymin <= tolerance or zmax - zmin <= tolerance:
        return None
    return (xmin, xmax, ymin, ymax, zmin, zmax)


def _subtract_aabb(target: Bounds, cutter: Bounds, *, tolerance: float = 1.0e-9) -> list[Bounds]:
    """Subtract cutter AABB from target AABB and return non-overlapping boxes.

    The decomposition is deterministic and conservative: it is meant as a safe
    fallback contract when native OCC/Gmsh booleans are unavailable.  It never
    claims exact BRep lineage.
    """

    inter = _intersection(target, cutter, tolerance=tolerance)
    if inter is None:
        return [target]
    tx0, tx1, ty0, ty1, tz0, tz1 = target
    ix0, ix1, iy0, iy1, iz0, iz1 = inter
    pieces: list[Bounds] = []
    # x slabs across full target y/z.
    if ix0 - tx0 > tolerance:
        pieces.append((tx0, ix0, ty0, ty1, tz0, tz1))
    if tx1 - ix1 > tolerance:
        pieces.append((ix1, tx1, ty0, ty1, tz0, tz1))
    # y slabs within the intersected x strip.
    if iy0 - ty0 > tolerance:
        pieces.append((ix0, ix1, ty0, iy0, tz0, tz1))
    if ty1 - iy1 > tolerance:
        pieces.append((ix0, ix1, iy1, ty1, tz0, tz1))
    # z slabs within intersected x/y column.
    if iz0 - tz0 > tolerance:
        pieces.append((ix0, ix1, iy0, iy1, tz0, iz0))
    if tz1 - iz1 > tolerance:
        pieces.append((ix0, ix1, iy0, iy1, iz1, tz1))
    return [piece for piece in pieces if _volume(piece) > tolerance]


@dataclass(slots=True)
class ImportedStructureSpec:
    id: str = ""
    name: str = ""
    kind: str = "diaphragm_wall"
    bounds: Bounds | None = None
    material_id: str = "concrete_c30"
    source_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ImportedStructureSpec":
        raw = dict(data or {})
        sid = _safe_id(raw.get("id") or raw.get("name") or raw.get("kind") or "structure", "structure")
        return cls(
            id=sid,
            name=str(raw.get("name") or sid),
            kind=str(raw.get("kind") or raw.get("semantic_type") or raw.get("role") or "diaphragm_wall"),
            bounds=None if raw.get("bounds") is None else _coerce_bounds(raw.get("bounds")),
            material_id=str(raw.get("material_id") or "concrete_c30"),
            source_path=str(raw.get("source_path") or raw.get("path") or ""),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "material_id": self.material_id,
            "source_path": self.source_path,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AssemblyOptions:
    boolean_mode: str = "aabb_fallback"
    remesh: bool = True
    element_size: float | None = None
    preserve_original_geology: bool = False
    tolerance: float = 1.0e-9
    require_native_boolean: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "AssemblyOptions":
        raw = dict(data or {})
        return cls(
            boolean_mode=str(raw.get("boolean_mode") or "aabb_fallback"),
            remesh=bool(raw.get("remesh", True)),
            element_size=None if raw.get("element_size") is None else float(raw.get("element_size")),
            preserve_original_geology=bool(raw.get("preserve_original_geology", False)),
            tolerance=float(raw.get("tolerance", 1.0e-9)),
            require_native_boolean=bool(raw.get("require_native_boolean", False)),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "boolean_mode": self.boolean_mode,
            "remesh": bool(self.remesh),
            "element_size": self.element_size,
            "preserve_original_geology": bool(self.preserve_original_geology),
            "tolerance": float(self.tolerance),
            "require_native_boolean": bool(self.require_native_boolean),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ImportDrivenAssemblyReport:
    contract: str = IMPORT_DRIVEN_ASSEMBLY_CONTRACT
    ok: bool = False
    strategy: str = "import_first_boolean_remesh"
    native_boolean_used: bool = False
    fallback_used: bool = True
    geology_source: str = ""
    structure_count: int = 0
    original_soil_volume_count: int = 0
    generated_soil_volume_count: int = 0
    consumed_soil_volume_ids: list[str] = field(default_factory=list)
    generated_soil_volume_ids: list[str] = field(default_factory=list)
    structure_volume_ids: list[str] = field(default_factory=list)
    mesh_report: dict[str, Any] = field(default_factory=dict)
    cad_fem_report: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "strategy": self.strategy,
            "native_boolean_used": bool(self.native_boolean_used),
            "fallback_used": bool(self.fallback_used),
            "geology_source": self.geology_source,
            "structure_count": int(self.structure_count),
            "original_soil_volume_count": int(self.original_soil_volume_count),
            "generated_soil_volume_count": int(self.generated_soil_volume_count),
            "consumed_soil_volume_ids": list(self.consumed_soil_volume_ids),
            "generated_soil_volume_ids": list(self.generated_soil_volume_ids),
            "structure_volume_ids": list(self.structure_volume_ids),
            "mesh_report": dict(self.mesh_report),
            "cad_fem_report": dict(self.cad_fem_report),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_import_driven_workflow_payload(project: Any | None = None) -> dict[str, Any]:
    volume_count = len(getattr(getattr(project, "geometry_model", None), "volumes", {}) or {}) if project is not None else 0
    return {
        "contract": IMPORT_DRIVEN_ASSEMBLY_CONTRACT,
        "recommended_strategy": "导入地质 STL/IFC 或钻孔表 → 导入围护结构 → 对结构与土体重叠区做布尔差分 → 重建物理组 → 重划分体网格",
        "why": [
            "当前鼠标 CAD 建模链路仍受 PyVista/VTK 事件、拾取和真实桌面图形栈影响，工程可用性不足。",
            "导入驱动路线把输入变成明确文件和参数，绕开复杂草图交互，更适合先形成地质-结构-FEM 前处理闭环。",
        ],
        "supported_geology_inputs": ["borehole_csv", "stl_geology", "msh_geology", "vtu_geology", "ifc_geology_experimental"],
        "supported_structure_inputs": ["ifc_structure", "stl_structure", "msh_structure", "vtu_structure", "box_bounds_surrogate"],
        "assembly_steps": [
            "import_geology",
            "import_or_register_support_structures",
            "classify_materials_by_strata_and_structure_kind",
            "boolean_subtract_structure_overlap_from_soil",
            "rebuild_cad_fem_physical_groups",
            "generate_conformal_tet4_mesh",
            "run_solver_readiness_precheck",
        ],
        "boolean_modes": ["aabb_fallback", "native_gmsh_occ_future", "native_occ_future"],
        "current_project_volume_count": volume_count,
        "gui_recommendation": "新增导入拼接工作流面板，优先走文件导入和重网格，不再依赖鼠标 CAD 建模作为主路径。",
    }


def create_geology_project_from_source(source: str | Path | Mapping[str, Any], *, source_type: str | None = None, options: Mapping[str, Any] | None = None, name: str | None = None) -> GeoProjectDocument:
    merged = dict(options or {})
    if name:
        merged.setdefault("name", name)
        merged.setdefault("project_name", name)
    result = geology_import.import_geology(source, source_type=source_type, options=merged)
    project = result.project
    project.metadata.setdefault("import_driven_workflow", {})["geology_import"] = result.to_dict()
    return project


def _ensure_structure_material(project: Any, material_id: str, *, kind: str) -> None:
    ensure_default_engineering_materials(project)
    if material_id in project.material_library.material_ids():
        return
    bucket_kind = "beam" if kind in {"beam", "anchor", "strut", "pile", "embedded_beam"} else "plate"
    material = MaterialRecord(
        id=material_id,
        name=material_id,
        model_type="elastic_beam" if bucket_kind == "beam" else "linear_elastic",
        parameters={"E": 3.0e7, "nu": 0.2} if bucket_kind == "plate" else {"EA": 1.0e6},
        drainage="not_applicable",
        metadata={"source": "import_driven_assembly", "kind": kind},
    )
    project.upsert_material(bucket_kind, material)


def register_structure_volume(project: Any, spec: ImportedStructureSpec | Mapping[str, Any]) -> GeometryVolume:
    item = spec if isinstance(spec, ImportedStructureSpec) else ImportedStructureSpec.from_mapping(spec)
    if item.bounds is None and item.source_path:
        # Lightweight STL structure fallback: use STL bounds and register as an imported structure volume.
        suffix = Path(item.source_path).suffix.lower()
        if suffix == ".stl":
            from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology
            stl = load_stl_geology(item.source_path, STLImportOptions(name=item.name or item.id, role=item.kind, material_id=item.material_id))
            item.bounds = _coerce_bounds(stl.bounds)
            item.metadata.setdefault("stl_summary", stl.to_summary_dict())
        elif suffix in {".msh", ".vtu"}:
            try:
                import meshio  # type: ignore
            except Exception as exc:  # pragma: no cover - environment dependent
                raise RuntimeError("导入结构 .msh/.vtu 需要 meshio；请在 ifc 环境安装 conda-forge meshio。") from exc
            mesh = meshio.read(item.source_path)
            points = list(getattr(mesh, "points", []) or [])
            if not points:
                raise ValueError(f"Imported structure {item.id} mesh has no points: {item.source_path}")
            xs = [float(row[0]) for row in points]
            ys = [float(row[1]) for row in points]
            zs = [float(row[2]) if len(row) > 2 else 0.0 for row in points]
            item.bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            item.metadata.setdefault("meshio_summary", {"source_path": item.source_path, "point_count": len(points), "cell_types": [str(getattr(block, "type", "unknown")) for block in list(getattr(mesh, "cells", []) or [])]})
        else:
            raise ValueError(f"Imported structure {item.id} needs bounds; direct {suffix} structure extraction is not available in this fallback path.")
    if item.bounds is None:
        raise ValueError(f"Imported structure {item.id} has no usable bounds.")
    _ensure_structure_material(project, item.material_id, kind=item.kind)
    volume_id = item.id if item.id.startswith("structure_") else f"structure_{item.id}"
    volume = GeometryVolume(
        id=volume_id,
        name=item.name or volume_id,
        bounds=item.bounds,
        role="structure" if item.kind not in {"excavation", "void"} else "excavation",
        material_id=item.material_id,
        metadata={
            "source": "import_driven_structure",
            "import_kind": item.kind,
            "source_path": item.source_path,
            "boolean_cutter": True,
            "preserve_as_structure": True,
            **dict(item.metadata),
        },
    )
    project.geometry_model.volumes[volume_id] = volume
    project.phase_manager.initial_phase.active_blocks.add(volume_id)
    structure_id = f"record_{volume_id}"
    if item.kind in {"excavation", "void"}:
        project.topology_graph.add_node(volume_id, "volume", label=volume.name, role="excavation")
    else:
        project.structure_model.plates[structure_id] = StructureRecord(
            id=structure_id,
            name=item.name or structure_id,
            geometry_ref=volume_id,
            material_id=item.material_id,
            active_stage_ids=[project.phase_manager.initial_phase.id],
            metadata={"source": "import_driven_structure", "semantic_type": item.kind, "volume_id": volume_id},
        )
        project.topology_graph.add_node(structure_id, "structure", label=item.name or structure_id, role=item.kind)
        project.topology_graph.add_edge(structure_id, volume_id, "generated_by", relation_group="structure_geometry")
    project.topology_graph.add_node(volume_id, "volume", label=volume.name, role=volume.role, material_id=item.material_id)
    project.topology_graph.add_node(item.material_id, "material", label=item.material_id)
    project.topology_graph.add_edge(volume_id, item.material_id, "mapped_to", relation_group="volume_material")
    project.mark_changed(["geometry", "structure", "material", "topology"], action="register_structure_volume", affected_entities=[volume_id])
    return volume


def register_structure_volumes(project: Any, specs: Iterable[ImportedStructureSpec | Mapping[str, Any]]) -> list[GeometryVolume]:
    rows = [register_structure_volume(project, spec) for spec in specs]
    project.metadata.setdefault("import_driven_workflow", {})["registered_structures"] = [row.to_dict() for row in rows]
    return rows


def _soil_volumes(project: Any) -> list[GeometryVolume]:
    rows: list[GeometryVolume] = []
    for volume in getattr(project.geometry_model, "volumes", {}).values():
        role = str(getattr(volume, "role", "") or "").lower()
        md = dict(getattr(volume, "metadata", {}) or {})
        if getattr(volume, "bounds", None) is None:
            continue
        if md.get("boolean_cutter"):
            continue
        if role in {"soil", "rock", "geology", "geological_volume"} or md.get("source") in {"borehole_csv", "stl_geology_loader"}:
            rows.append(volume)
    return rows


def _structure_cutters(project: Any) -> list[GeometryVolume]:
    rows: list[GeometryVolume] = []
    for volume in getattr(project.geometry_model, "volumes", {}).values():
        md = dict(getattr(volume, "metadata", {}) or {})
        role = str(getattr(volume, "role", "") or "").lower()
        if getattr(volume, "bounds", None) is None:
            continue
        if md.get("boolean_cutter") or role in {"structure", "excavation", "void", "wall"}:
            rows.append(volume)
    return rows


def subtract_structure_overlaps_from_geology(project: Any, *, options: AssemblyOptions | Mapping[str, Any] | None = None) -> ImportDrivenAssemblyReport:
    opts = options if isinstance(options, AssemblyOptions) else AssemblyOptions.from_mapping(options)
    blockers: list[str] = []
    warnings: list[str] = []
    if opts.require_native_boolean:
        blockers.append("native boolean was required, but this import-driven path currently provides an explicit AABB fallback contract only")
        return ImportDrivenAssemblyReport(ok=False, blockers=blockers, warnings=warnings, metadata={"options": opts.to_dict()})

    soils = _soil_volumes(project)
    cutters = _structure_cutters(project)
    if not soils:
        blockers.append("no soil/geology volumes were found; import borehole CSV or closed geology STL first")
    if not cutters:
        warnings.append("no structure/excavation cutter volumes were found; meshing will use imported geology volumes unchanged")
    if blockers:
        return ImportDrivenAssemblyReport(ok=False, blockers=blockers, warnings=warnings, metadata={"options": opts.to_dict()})

    original_ids = [v.id for v in soils]
    generated: dict[str, GeometryVolume] = {}
    consumed: list[str] = []
    for soil in soils:
        pieces = [tuple(float(v) for v in soil.bounds)]  # type: ignore[arg-type]
        for cutter in cutters:
            next_pieces: list[Bounds] = []
            cutter_bounds = tuple(float(v) for v in cutter.bounds)  # type: ignore[arg-type]
            for piece in pieces:
                next_pieces.extend(_subtract_aabb(piece, cutter_bounds, tolerance=opts.tolerance))
            pieces = next_pieces
        if len(pieces) == 1 and pieces[0] == tuple(float(v) for v in soil.bounds):  # type: ignore[arg-type]
            generated[soil.id] = soil
            continue
        consumed.append(soil.id)
        for index, piece in enumerate(pieces, start=1):
            gid = _safe_id(f"{soil.id}_cut_{index:02d}", "soil_cut")
            while gid in project.geometry_model.volumes or gid in generated:
                gid = f"{gid}_x"
            generated[gid] = GeometryVolume(
                id=gid,
                name=f"{soil.name} cut {index}",
                bounds=piece,
                surface_ids=list(getattr(soil, "surface_ids", []) or []),
                role=getattr(soil, "role", "soil") or "soil",
                material_id=getattr(soil, "material_id", None),
                metadata={
                    **dict(getattr(soil, "metadata", {}) or {}),
                    "source": "import_driven_boolean_subtract",
                    "parent_volume_id": soil.id,
                    "boolean_mode": opts.boolean_mode,
                    "native_boolean_used": False,
                    "fallback_used": True,
                },
            )

    if not opts.preserve_original_geology:
        for sid in consumed:
            project.geometry_model.volumes.pop(sid, None)
            project.phase_manager.initial_phase.active_blocks.discard(sid)
    for gid, volume in generated.items():
        project.geometry_model.volumes[gid] = volume
        if volume.role in {"soil", "rock", "geology", "geological_volume"}:
            project.phase_manager.initial_phase.active_blocks.add(gid)
            project.topology_graph.add_node(gid, "volume", label=volume.name, role=volume.role, material_id=volume.material_id)
            if volume.material_id:
                project.topology_graph.add_edge(gid, str(volume.material_id), "mapped_to", relation_group="volume_material")
    # Update clusters: replace consumed parent volume ids with generated children.
    generated_by_parent: dict[str, list[str]] = {}
    for volume in generated.values():
        parent = str(dict(volume.metadata).get("parent_volume_id") or "")
        if parent:
            generated_by_parent.setdefault(parent, []).append(volume.id)
    for cluster in project.soil_model.soil_clusters.values():
        new_ids: list[str] = []
        for vid in list(cluster.volume_ids):
            if vid in generated_by_parent:
                new_ids.extend(generated_by_parent[vid])
            elif vid in project.geometry_model.volumes:
                new_ids.append(vid)
        if new_ids:
            cluster.volume_ids = list(dict.fromkeys(new_ids))
    project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
    project.mesh_model.mesh_settings.metadata.update({
        "requires_volume_meshing": True,
        "requires_volume_remesh": True,
        "boolean_subtract_mode": opts.boolean_mode,
    })
    auto_assign_materials_by_recognized_strata_and_structures(project, overwrite=False)

    mesh_report: dict[str, Any] = {}
    if opts.remesh:
        _mesh, report = generate_geoproject_gmsh_occ_tet4_mesh(project, attach=True, element_size=opts.element_size, require_native=False)
        mesh_report = report.to_dict()
    cad_fem = build_cad_fem_preprocessor(project).to_dict()
    readiness_raw = validate_cad_fem_preprocessor(project)
    readiness = readiness_raw.to_dict() if hasattr(readiness_raw, "to_dict") else dict(readiness_raw)
    cad_fem_report = {"preprocessor": cad_fem, "readiness": readiness}
    # Treat import/cut assembly as successful when geometry/cutter registration and
    # deterministic subtraction completed.  CAD-FEM readiness may still be blocked
    # before topology identities or a volume mesh are generated; that status is
    # reported separately in cad_fem_report and should not make an STL/IFC import
    # button look like it did nothing.
    ok = not blockers and bool(generated or cutters or project.mesh_model.mesh_document is not None or cad_fem.get("physical_groups"))
    report = ImportDrivenAssemblyReport(
        ok=ok,
        native_boolean_used=False,
        fallback_used=True,
        geology_source=str(project.metadata.get("source", project.project_settings.metadata.get("source", "project"))),
        structure_count=len(cutters),
        original_soil_volume_count=len(original_ids),
        generated_soil_volume_count=len([v for v in generated.values() if v.role in {"soil", "rock", "geology", "geological_volume"}]),
        consumed_soil_volume_ids=consumed,
        generated_soil_volume_ids=[v.id for v in generated.values() if v.role in {"soil", "rock", "geology", "geological_volume"}],
        structure_volume_ids=[v.id for v in cutters],
        mesh_report=mesh_report,
        cad_fem_report=cad_fem_report,
        blockers=blockers,
        warnings=warnings,
        metadata={"options": opts.to_dict(), "original_soil_volume_ids": original_ids},
    )
    project.metadata.setdefault("import_driven_workflow", {})["last_assembly_report"] = report.to_dict()
    project.mark_changed(["geometry", "mesh", "soil", "structure"], action="subtract_structure_overlaps_from_geology", affected_entities=report.generated_soil_volume_ids + report.structure_volume_ids)
    return report


def run_import_driven_assembly(
    *,
    geology_source: str | Path | Mapping[str, Any] | None = None,
    geology_source_type: str | None = None,
    geology_options: Mapping[str, Any] | None = None,
    project: Any | None = None,
    structure_specs: Sequence[ImportedStructureSpec | Mapping[str, Any]] | None = None,
    options: AssemblyOptions | Mapping[str, Any] | None = None,
    name: str | None = None,
) -> tuple[GeoProjectDocument, ImportDrivenAssemblyReport]:
    if project is None:
        if geology_source is None:
            project = GeoProjectDocument.create_empty(name=name or "import-driven-assembly")
        else:
            project = create_geology_project_from_source(geology_source, source_type=geology_source_type, options=geology_options, name=name)
    ensure_default_engineering_materials(project)
    if structure_specs:
        register_structure_volumes(project, structure_specs)
    report = subtract_structure_overlaps_from_geology(project, options=options)
    return project, report


__all__ = [
    "IMPORT_DRIVEN_ASSEMBLY_CONTRACT",
    "AssemblyOptions",
    "ImportedStructureSpec",
    "ImportDrivenAssemblyReport",
    "build_import_driven_workflow_payload",
    "create_geology_project_from_source",
    "register_structure_volume",
    "register_structure_volumes",
    "run_import_driven_assembly",
    "subtract_structure_overlaps_from_geology",
]
