from __future__ import annotations

"""1.4.2c native Gmsh/OCC boolean + physical-group mesh roundtrip.

This service is intentionally stricter than the 1.4.2a CAD facade.  It can run
an actual gmsh.model.occ boolean/fragment/mesh roundtrip when gmsh is available,
while still providing an explicitly labelled deterministic contract path for CI
or machines without gmsh.  The deterministic path is never reported as native.
"""

from dataclasses import dataclass, field
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable

from geoai_simkit.commands.cad_kernel_commands import ExecuteCadFeaturesCommand
from geoai_simkit.commands.command_stack import CommandStack
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap
from geoai_simkit.services.gmsh_occ_project_mesher import generate_geoproject_gmsh_occ_tet4_mesh


@dataclass(slots=True)
class GmshOccRoundtripCapability:
    contract: str = "geoai_simkit_gmsh_occ_boolean_roundtrip_capability_v1"
    ok: bool = True
    gmsh_available: bool = False
    gmsh_occ_available: bool = False
    meshio_available: bool = False
    selected_backend: str = "deterministic_tet4_contract"
    native_roundtrip_possible: bool = False
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "gmsh_available": bool(self.gmsh_available),
            "gmsh_occ_available": bool(self.gmsh_occ_available),
            "meshio_available": bool(self.meshio_available),
            "selected_backend": self.selected_backend,
            "native_roundtrip_possible": bool(self.native_roundtrip_possible),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PhysicalGroupRoundtripRecord:
    id: str
    dimension: int
    entity_ids: list[int] = field(default_factory=list)
    cell_ids: list[int] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)
    source_volume_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": int(self.dimension),
            "entity_ids": [int(v) for v in self.entity_ids],
            "cell_ids": [int(v) for v in self.cell_ids],
            "material_ids": list(self.material_ids),
            "source_volume_ids": list(self.source_volume_ids),
        }


@dataclass(slots=True)
class GmshOccBooleanMeshRoundtripReport:
    contract: str = "geoai_simkit_gmsh_occ_boolean_mesh_roundtrip_v1"
    ok: bool = False
    status: str = "rejected"
    backend: str = "deterministic_tet4_contract"
    native_backend_used: bool = False
    fallback_used: bool = True
    native_required: bool = False
    boolean_report: dict[str, Any] = field(default_factory=dict)
    node_count: int = 0
    cell_count: int = 0
    physical_group_count: int = 0
    imported_group_count: int = 0
    generated_volume_ids: list[str] = field(default_factory=list)
    consumed_volume_ids: list[str] = field(default_factory=list)
    physical_groups: list[dict[str, Any]] = field(default_factory=list)
    msh_path: str = ""
    manifest_path: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "status": self.status,
            "backend": self.backend,
            "native_backend_used": bool(self.native_backend_used),
            "fallback_used": bool(self.fallback_used),
            "native_required": bool(self.native_required),
            "boolean_report": dict(self.boolean_report),
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "physical_group_count": int(self.physical_group_count),
            "imported_group_count": int(self.imported_group_count),
            "generated_volume_ids": list(self.generated_volume_ids),
            "consumed_volume_ids": list(self.consumed_volume_ids),
            "physical_groups": [dict(row) for row in self.physical_groups],
            "msh_path": self.msh_path,
            "manifest_path": self.manifest_path,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def probe_gmsh_occ_boolean_roundtrip() -> GmshOccRoundtripCapability:
    warnings: list[str] = []
    gmsh_available = _has_module("gmsh")
    meshio_available = _has_module("meshio")
    gmsh_occ_available = False
    gmsh_version = ""
    if gmsh_available:
        try:
            import gmsh  # type: ignore
            gmsh_version = str(getattr(gmsh, "__version__", ""))
            gmsh_occ_available = hasattr(getattr(gmsh, "model", None), "occ")
        except Exception as exc:
            gmsh_available = False
            gmsh_occ_available = False
            warnings.append(f"gmsh import failed: {type(exc).__name__}: {exc}")
    if not gmsh_occ_available:
        warnings.append("Native gmsh.model.occ is unavailable; native boolean mesh roundtrip cannot execute in this environment.")
    if not meshio_available:
        warnings.append("meshio is unavailable; native .msh import/export verification will be limited to gmsh API/manifest data.")
    native_possible = bool(gmsh_available and gmsh_occ_available)
    return GmshOccRoundtripCapability(
        ok=True,
        gmsh_available=gmsh_available,
        gmsh_occ_available=gmsh_occ_available,
        meshio_available=meshio_available,
        selected_backend="gmsh_occ_native_roundtrip" if native_possible else "deterministic_tet4_contract",
        native_roundtrip_possible=native_possible,
        warnings=warnings,
        metadata={"gmsh_version": gmsh_version, "release_gate": "1.4.2c", "native_required_for_certified_roundtrip": True},
    )


def _visible_volumes(project: Any) -> list[Any]:
    rows = []
    for volume in list(getattr(getattr(project, "geometry_model", None), "volumes", {}).values()):
        if getattr(volume, "bounds", None) is None:
            continue
        if dict(getattr(volume, "metadata", {}) or {}).get("visible", True) is False:
            continue
        rows.append(volume)
    return rows


def _manifest_from_mesh(project: Any, *, native: bool, backend: str) -> dict[str, Any]:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    groups: dict[str, dict[str, Any]] = {}
    if mesh is not None:
        cell_tags = dict(getattr(mesh, "cell_tags", {}) or {})
        physical = list(cell_tags.get("physical_volume", cell_tags.get("block_id", [])) or [])
        material = list(cell_tags.get("material_id", []) or [])
        for cell_id, gid_raw in enumerate(physical):
            gid = str(gid_raw)
            row = groups.setdefault(gid, {"id": gid, "dimension": 3, "cell_ids": [], "material_ids": set(), "source_volume_ids": set()})
            row["cell_ids"].append(cell_id)
            row["source_volume_ids"].add(gid)
            if cell_id < len(material) and str(material[cell_id]):
                row["material_ids"].add(str(material[cell_id]))
    physical_groups = []
    for row in sorted(groups.values(), key=lambda r: str(r["id"])):
        physical_groups.append({
            "id": row["id"],
            "dimension": int(row["dimension"]),
            "cell_ids": list(row["cell_ids"]),
            "material_ids": sorted(row["material_ids"]),
            "source_volume_ids": sorted(row["source_volume_ids"]),
        })
    return {
        "contract": "geoai_simkit_gmsh_occ_physical_group_roundtrip_manifest_v1",
        "native_backend_used": bool(native),
        "backend": backend,
        "node_count": 0 if mesh is None else mesh.node_count,
        "cell_count": 0 if mesh is None else mesh.cell_count,
        "cell_types": [] if mesh is None else sorted(set(mesh.cell_types)),
        "physical_groups": physical_groups,
    }


def _write_manifest(project: Any, output_dir: str | Path | None, *, stem: str, native: bool, backend: str) -> tuple[str, dict[str, Any]]:
    manifest = _manifest_from_mesh(project, native=native, backend=backend)
    if output_dir is None:
        return "", manifest
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}_physical_groups.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path), manifest


def _aabb_roundtrip(
    project: Any,
    *,
    output_dir: str | Path | None,
    stem: str,
    element_size: float | None,
    boolean_report: dict[str, Any],
    native_required: bool,
) -> GmshOccBooleanMeshRoundtripReport:
    mesh, mesh_report = generate_geoproject_gmsh_occ_tet4_mesh(project, attach=True, element_size=element_size, require_native=False)
    manifest_path, manifest = _write_manifest(project, output_dir, stem=stem, native=False, backend="deterministic_tet4_contract")
    msh_path = ""
    if output_dir is not None:
        root = Path(output_dir)
        msh = root / f"{stem}.msh.json"
        msh.write_text(json.dumps({"mesh_roundtrip": manifest, "note": "Deterministic Tet4 contract; not a native gmsh .msh file."}, ensure_ascii=False, indent=2), encoding="utf-8")
        msh_path = str(msh)
    warnings = list(mesh_report.warnings)
    warnings.append("Native gmsh/OCC was not used; deterministic Tet4 physical-group contract was generated instead.")
    status = "rejected_native_required" if native_required else "accepted_1_4_2c_roundtrip_contract"
    ok = bool(mesh.cell_count) and not native_required
    return GmshOccBooleanMeshRoundtripReport(
        ok=ok,
        status=status,
        backend="deterministic_tet4_contract",
        native_backend_used=False,
        fallback_used=True,
        native_required=native_required,
        boolean_report=boolean_report,
        node_count=mesh.node_count,
        cell_count=mesh.cell_count,
        physical_group_count=len(manifest.get("physical_groups", [])),
        imported_group_count=len(manifest.get("physical_groups", [])),
        generated_volume_ids=list(boolean_report.get("generated_volume_ids", [])),
        consumed_volume_ids=list(boolean_report.get("consumed_volume_ids", [])),
        physical_groups=list(manifest.get("physical_groups", [])),
        msh_path=msh_path,
        manifest_path=manifest_path,
        warnings=warnings,
        metadata={"native_certified": False, "mesh_report": mesh_report.to_dict(), "roundtrip_mode": "contract_surrogate"},
    )


def _native_roundtrip(
    project: Any,
    *,
    output_dir: str | Path | None,
    stem: str,
    element_size: float | None,
    boolean_report: dict[str, Any],
) -> GmshOccBooleanMeshRoundtripReport:
    import gmsh  # type: ignore

    root = Path(output_dir) if output_dir is not None else None
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    initialized_here = False
    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    block_tags: list[str] = []
    material_tags: list[str] = []
    physical_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    warnings: list[str] = []
    physical_group_rows: list[dict[str, Any]] = []
    msh_path = ""
    try:
        try:
            gmsh.initialize()
            initialized_here = True
        except Exception:
            initialized_here = False
        gmsh.model.add(f"geoai_142c_{stem}")
        if element_size is not None:
            try:
                gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(element_size))
                gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(element_size) * 0.25)
            except Exception as exc:
                warnings.append(f"Failed to set gmsh characteristic length: {type(exc).__name__}: {exc}")
        volume_entity_by_id: dict[str, tuple[int, int]] = {}
        for volume in _visible_volumes(project):
            b = tuple(float(v) for v in volume.bounds)
            x0, x1, y0, y1, z0, z1 = b
            if x1 <= x0 or y1 <= y0 or z1 <= z0:
                warnings.append(f"volume {volume.id} has non-positive bounds and was skipped")
                continue
            tag = gmsh.model.occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
            volume_entity_by_id[str(volume.id)] = (3, int(tag))
        if not volume_entity_by_id:
            raise RuntimeError("No visible volumes are available for native gmsh/OCC roundtrip.")
        # Fragment visible volumes so adjacent/overlapping bodies get a valid OCC topology.
        try:
            dimtags = list(volume_entity_by_id.values())
            gmsh.model.occ.fragment(dimtags, [])
        except Exception as exc:
            warnings.append(f"gmsh OCC fragment failed; proceeding with individual volume entities: {type(exc).__name__}: {exc}")
        gmsh.model.occ.synchronize()
        # Re-query entities by bbox center. Fragment can replace tags, so use bbox containment to bind physical groups.
        native_entities = list(gmsh.model.getEntities(3))
        physical_by_block: dict[str, list[int]] = {vid: [] for vid in volume_entity_by_id}
        for entity_dim, entity_tag in native_entities:
            try:
                bb = gmsh.model.getBoundingBox(entity_dim, entity_tag)
                cx = (float(bb[0]) + float(bb[3])) * 0.5
                cy = (float(bb[1]) + float(bb[4])) * 0.5
                cz = (float(bb[2]) + float(bb[5])) * 0.5
            except Exception:
                continue
            for volume in _visible_volumes(project):
                x0, x1, y0, y1, z0, z1 = tuple(float(v) for v in volume.bounds)
                eps = 1.0e-7
                if x0 - eps <= cx <= x1 + eps and y0 - eps <= cy <= y1 + eps and z0 - eps <= cz <= z1 + eps:
                    physical_by_block.setdefault(str(volume.id), []).append(int(entity_tag))
                    break
        group_tag_by_block: dict[str, int] = {}
        next_tag = 1
        for block_id, entity_tags in sorted(physical_by_block.items()):
            if not entity_tags:
                continue
            tag = next_tag
            next_tag += 1
            try:
                gmsh.model.addPhysicalGroup(3, entity_tags, tag=tag)
            except TypeError:
                tag = int(gmsh.model.addPhysicalGroup(3, entity_tags))
            gmsh.model.setPhysicalName(3, tag, block_id)
            group_tag_by_block[block_id] = int(tag)
        if not group_tag_by_block:
            raise RuntimeError("No gmsh physical volume groups could be created.")
        gmsh.model.mesh.generate(3)
        if root is not None:
            msh = root / f"{stem}.msh"
            gmsh.write(str(msh))
            msh_path = str(msh)
        node_tags, coords, _params = gmsh.model.mesh.getNodes()
        node_id_by_tag: dict[int, int] = {}
        coord_list = list(coords)
        for idx, tag in enumerate(list(node_tags)):
            xyz = tuple(float(v) for v in coord_list[idx * 3:idx * 3 + 3])
            node_id_by_tag[int(tag)] = len(nodes)
            nodes.append(xyz)
        # Gmsh element type 4 is first-order tetrahedron. We import only tet4 cells for solver consistency.
        for block_id, entity_tags in sorted(physical_by_block.items()):
            material_id = ""
            volume = getattr(project.geometry_model, "volumes", {}).get(block_id)
            if volume is not None and getattr(volume, "material_id", None):
                material_id = str(volume.material_id)
            for entity_tag in entity_tags:
                types, elem_tags, elem_nodes = gmsh.model.mesh.getElements(3, entity_tag)
                for etype, e_tags, e_nodes in zip(types, elem_tags, elem_nodes):
                    if int(etype) != 4:
                        continue
                    flat = [int(v) for v in list(e_nodes)]
                    for i in range(0, len(flat), 4):
                        raw = flat[i:i + 4]
                        if len(raw) != 4:
                            continue
                        try:
                            conn = tuple(node_id_by_tag[n] for n in raw)
                        except KeyError:
                            continue
                        cid = len(cells)
                        cells.append(conn)
                        cell_types.append("tet4")
                        block_tags.append(block_id)
                        material_tags.append(material_id)
                        physical_tags.append(block_id)
                        block_to_cells.setdefault(block_id, []).append(cid)
        if not cells:
            raise RuntimeError("Native gmsh mesh generation produced no tet4 cells.")
        mesh = MeshDocument(
            nodes=nodes,
            cells=cells,
            cell_types=cell_types,
            cell_tags={"block_id": block_tags, "material_id": material_tags, "physical_volume": physical_tags, "region_name": block_tags},
            entity_map=MeshEntityMap(block_to_cells=block_to_cells, metadata={"source": "execute_gmsh_occ_boolean_mesh_roundtrip", "native_backend_used": True}),
            quality=MeshQualityReport(min_quality=None, max_aspect_ratio=None, bad_cell_ids=[], warnings=warnings),
            metadata={"mesher": "gmsh_occ_native_roundtrip", "production_ready": True, "preview": False, "native_backend_used": True, "fallback_used": False, "release_gate": "1.4.2c_native_roundtrip"},
        )
        project.mesh_model.attach_mesh(mesh)
        manifest_path, manifest = _write_manifest(project, output_dir, stem=stem, native=True, backend="gmsh_occ_native_roundtrip")
        physical_group_rows = list(manifest.get("physical_groups", []))
        return GmshOccBooleanMeshRoundtripReport(
            ok=True,
            status="accepted_1_4_2c_native_roundtrip",
            backend="gmsh_occ_native_roundtrip",
            native_backend_used=True,
            fallback_used=False,
            boolean_report=boolean_report,
            node_count=mesh.node_count,
            cell_count=mesh.cell_count,
            physical_group_count=len(physical_group_rows),
            imported_group_count=len(physical_group_rows),
            generated_volume_ids=list(boolean_report.get("generated_volume_ids", [])),
            consumed_volume_ids=list(boolean_report.get("consumed_volume_ids", [])),
            physical_groups=physical_group_rows,
            msh_path=msh_path,
            manifest_path=manifest_path,
            warnings=warnings,
            metadata={"native_certified": True, "roundtrip_mode": "native_gmsh_occ_api", "group_tag_by_block": group_tag_by_block},
        )
    finally:
        if initialized_here:
            try:
                gmsh.finalize()
            except Exception:
                pass


def execute_gmsh_occ_boolean_mesh_roundtrip(
    project: Any,
    *,
    output_dir: str | Path | None = None,
    stem: str = "release_1_4_2c_gmsh_occ",
    element_size: float | None = None,
    require_native: bool = False,
    allow_contract_fallback: bool = True,
    execute_boolean_features: bool = True,
    attach: bool = True,
) -> GmshOccBooleanMeshRoundtripReport:
    """Execute deferred boolean features and roundtrip physical-group Tet4 mesh.

    When ``require_native`` is True, the function fails unless an actual
    gmsh.model.occ backend is importable and used.  When False, the deterministic
    Tet4 contract path is permitted but explicitly labelled as fallback.
    """

    capability = probe_gmsh_occ_boolean_roundtrip()
    boolean_report: dict[str, Any] = {}
    warnings: list[str] = []
    if execute_boolean_features:
        stack = CommandStack()
        result = stack.execute(ExecuteCadFeaturesCommand(require_native=require_native, allow_fallback=allow_contract_fallback), project)
        boolean_report = dict(result.metadata or {})
        if not result.ok:
            raise RuntimeError(result.message or "CAD boolean feature execution failed before mesh roundtrip")
    else:
        boolean_report = dict(getattr(project.geometry_model, "metadata", {}).get("last_cad_occ_feature_execution", {}) or {})
    if require_native and not capability.native_roundtrip_possible:
        raise RuntimeError("1.4.2c native gmsh/OCC roundtrip was required but gmsh.model.occ is unavailable.")
    if capability.native_roundtrip_possible:
        try:
            report = _native_roundtrip(project, output_dir=output_dir, stem=stem, element_size=element_size, boolean_report=boolean_report)
        except Exception as exc:
            if require_native or not allow_contract_fallback:
                raise
            warnings.append(f"Native gmsh/OCC roundtrip failed, using deterministic contract fallback: {type(exc).__name__}: {exc}")
            report = _aabb_roundtrip(project, output_dir=output_dir, stem=stem, element_size=element_size, boolean_report=boolean_report, native_required=False)
            report.warnings.extend(warnings)
    else:
        report = _aabb_roundtrip(project, output_dir=output_dir, stem=stem, element_size=element_size, boolean_report=boolean_report, native_required=require_native)
    if attach:
        project.mesh_model.metadata["last_gmsh_occ_boolean_mesh_roundtrip"] = report.to_dict()
        project.metadata["release_1_4_2c_gmsh_occ_boolean_roundtrip"] = report.to_dict()
        try:
            from geoai_simkit.services.cad_shape_store_service import build_cad_shape_store
            shape_report = build_cad_shape_store(project, output_dir=output_dir, attach=True, include_roundtrip=True, export_references=True)
            project.metadata["release_1_4_2d_cad_shape_store_build"] = shape_report.to_dict()
        except Exception as exc:
            project.metadata["release_1_4_2d_cad_shape_store_build_error"] = f"{type(exc).__name__}: {exc}"
        if hasattr(project, "mark_changed"):
            project.mark_changed(["geometry", "topology", "mesh", "solver", "result", "cad_shape_store"], action="execute_gmsh_occ_boolean_mesh_roundtrip", affected_entities=list(report.generated_volume_ids) + list(report.consumed_volume_ids))
    return report


__all__ = [
    "GmshOccRoundtripCapability",
    "GmshOccBooleanMeshRoundtripReport",
    "PhysicalGroupRoundtripRecord",
    "probe_gmsh_occ_boolean_roundtrip",
    "execute_gmsh_occ_boolean_mesh_roundtrip",
]
