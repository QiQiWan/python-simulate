from __future__ import annotations

"""Headless geometry-kernel service for STL optimization and soil-layer cutting."""

from collections import defaultdict
import importlib.util
import math
import shutil
from typing import Iterable, Mapping, Sequence, Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts.geometry_kernel import (
    GeometryKernelDependencyStatus,
    GeometryKernelReport,
    GmshOCCFragmentMeshingReport,
    LocalRemeshReport,
    GmshMeshioValidationReport,
    GmshPhysicalGroupRecord,
    MeshQualityOptimizationReport,
    STLOptimizationAction,
    STLOptimizationReport,
    SoilLayerCutReport,
    SoilLayerDefinition,
    StratigraphicClosureReport,
    SurfaceStratigraphyDefinition,
)
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.complete_3d import apply_3d_boundary_tags
from geoai_simkit.diagnostics.operation_log import geometry_log_status as _geometry_log_status, log_geometry_operation


def geometry_kernel_dependency_status() -> GeometryKernelDependencyStatus:
    gmsh_spec = importlib.util.find_spec("gmsh")
    meshio_spec = importlib.util.find_spec("meshio")
    gmsh_exe = shutil.which("gmsh") or shutil.which("gmsh.exe")
    diagnostics: list[str] = []
    if gmsh_spec is None and gmsh_exe is None:
        diagnostics.append("Gmsh is not installed; production conformal Tet4 meshing will use dependency-light fallbacks only.")
    if meshio_spec is None:
        diagnostics.append("meshio is not installed; Gmsh .msh conversion to MeshDocument is unavailable.")
    production = bool((gmsh_spec is not None or gmsh_exe is not None) and meshio_spec is not None)
    return GeometryKernelDependencyStatus(
        gmsh_python_available=gmsh_spec is not None,
        gmsh_executable_available=gmsh_exe is not None,
        meshio_available=meshio_spec is not None,
        backend="gmsh_meshio" if production else "dependency_light",
        status="available" if production else "fallback",
        diagnostics=tuple(diagnostics),
        metadata={"gmsh_executable": gmsh_exe or ""},
    )


def _current_mesh(project_or_mesh: object) -> MeshDocument | None:
    if isinstance(project_or_mesh, MeshDocument):
        return project_or_mesh
    context = as_project_context(project_or_mesh)
    mesh = context.current_mesh()
    return mesh if isinstance(mesh, MeshDocument) else None


def _triangle_area(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    ax, ay, az = float(a[0]), float(a[1]), float(a[2])
    bx, by, bz = float(b[0]), float(b[1]), float(b[2])
    cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)


def _edge_counts(mesh: MeshDocument) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for cell, ctype in zip(mesh.cells, mesh.cell_types or ["tri3"] * mesh.cell_count):
        if str(ctype).lower() != "tri3" or len(cell) < 3:
            continue
        tri = tuple(int(v) for v in cell[:3])
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            counts[(min(a, b), max(a, b))] += 1
    return dict(counts)


def _stl_counts(mesh: MeshDocument) -> tuple[int, int, int, bool, bool]:
    counts = _edge_counts(mesh)
    open_edges = sum(1 for value in counts.values() if value == 1)
    nonmanifold = sum(1 for value in counts.values() if value > 2)
    tri_count = sum(1 for item in mesh.cell_types or [] if str(item).lower() == "tri3")
    closed = bool(tri_count > 0 and open_edges == 0 and nonmanifold == 0)
    manifold = bool(tri_count > 0 and nonmanifold == 0)
    return open_edges, nonmanifold, tri_count, closed, manifold


def optimize_stl_surface_mesh(project_or_mesh: object, *, tolerance: float = 1.0e-9, attach: bool = False) -> tuple[MeshDocument | None, STLOptimizationReport]:
    mesh = _current_mesh(project_or_mesh)
    if mesh is None:
        report = STLOptimizationReport(ok=False, actions=(STLOptimizationAction("mesh.missing", "No MeshDocument is attached to the project.", "error"),))
        return None, report
    tol = max(float(tolerance), 1.0e-15)
    original_nodes = int(mesh.node_count)
    original_faces = int(mesh.cell_count)

    node_map: dict[tuple[int, int, int], int] = {}
    old_to_new: dict[int, int] = {}
    nodes: list[tuple[float, float, float]] = []
    for idx, raw in enumerate(mesh.nodes):
        key = (round(float(raw[0]) / tol), round(float(raw[1]) / tol), round(float(raw[2]) / tol))
        if key not in node_map:
            node_map[key] = len(nodes)
            nodes.append((float(raw[0]), float(raw[1]), float(raw[2])))
        old_to_new[int(idx)] = node_map[key]

    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    kept_old_indices: list[int] = []
    degenerate = 0
    for cid, cell in enumerate(mesh.cells):
        ctype = str((mesh.cell_types or ["tri3"] * mesh.cell_count)[cid]).lower()
        mapped = tuple(old_to_new[int(v)] for v in cell)
        if ctype == "tri3":
            if len(set(mapped[:3])) < 3 or _triangle_area(nodes[mapped[0]], nodes[mapped[1]], nodes[mapped[2]]) <= tol * tol:
                degenerate += 1
                continue
        cells.append(mapped)
        cell_types.append(ctype)
        kept_old_indices.append(cid)

    cell_tags: dict[str, list[object]] = {}
    for key, values in mesh.cell_tags.items():
        vals = list(values)
        cell_tags[key] = [vals[i] if i < len(vals) else (vals[-1] if vals else "") for i in kept_old_indices]
    if "role" not in cell_tags:
        cell_tags["role"] = ["geology_surface"] * len(cells)
    optimized = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags=cell_tags,
        face_tags=dict(mesh.face_tags),
        node_tags={},
        quality=MeshQualityReport(min_quality=1.0 if degenerate == 0 else 0.0, warnings=[] if degenerate == 0 else [f"Removed {degenerate} degenerate STL face(s)."]),
        metadata={
            **dict(mesh.metadata),
            "source": "geometry_kernel_stl_optimizer",
            "mesh_role": "geometry_surface",
            "mesh_dimension": 2,
            "surface_mesh_only": True,
            "requires_volume_meshing": True,
            "solid_solver_ready": False,
            "geometry_kernel_optimized": True,
            "stl_optimization_tolerance": tol,
        },
    )
    open_edges, nonmanifold, tri_count, closed, manifold = _stl_counts(optimized)
    duplicate_count = original_nodes - int(optimized.node_count)
    actions: list[STLOptimizationAction] = []
    if duplicate_count:
        actions.append(STLOptimizationAction("stl.duplicate_nodes_merged", "Merged duplicate or near-duplicate STL nodes.", "info", duplicate_count))
    if degenerate:
        actions.append(STLOptimizationAction("stl.degenerate_faces_removed", "Removed zero-area or collapsed STL triangles.", "warning", degenerate))
    if open_edges:
        actions.append(STLOptimizationAction("stl.open_boundary_edges", "STL shell still has open boundary edges and needs repair before conformal volume meshing.", "error", open_edges))
    if nonmanifold:
        actions.append(STLOptimizationAction("stl.nonmanifold_edges", "STL shell still has non-manifold edges and needs topological repair.", "error", nonmanifold))
    if closed and manifold:
        actions.append(STLOptimizationAction("stl.closed_manifold", "STL shell is closed and manifold after optimization.", "info", tri_count))
    report = STLOptimizationReport(
        ok=bool(not open_edges and not nonmanifold and int(optimized.cell_count) > 0),
        original_node_count=original_nodes,
        optimized_node_count=int(optimized.node_count),
        original_face_count=original_faces,
        optimized_face_count=int(optimized.cell_count),
        duplicate_node_count=duplicate_count,
        degenerate_face_count=degenerate,
        open_boundary_edge_count=open_edges,
        nonmanifold_edge_count=nonmanifold,
        closed=closed,
        manifold=manifold,
        actions=tuple(actions),
        metadata={"contract_version": "stl_optimization_report_v1"},
    )
    optimized.metadata["stl_optimization"] = report.to_dict()
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.attach_mesh(optimized)
    return optimized, report


def _mesh_bounds(mesh: MeshDocument) -> tuple[float, float, float, float, float, float]:
    xs = [float(row[0]) for row in mesh.nodes]
    ys = [float(row[1]) for row in mesh.nodes]
    zs = [float(row[2]) for row in mesh.nodes]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)) if xs else (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def normalize_soil_layers(layers: Iterable[Mapping[str, object]], *, bounds: tuple[float, float, float, float, float, float]) -> tuple[SoilLayerDefinition, ...]:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    rows: list[SoilLayerDefinition] = []
    for idx, raw in enumerate(layers):
        if "z_min" in raw and "z_max" in raw:
            a = float(raw["z_min"])
            b = float(raw["z_max"])
        elif "top" in raw and "bottom" in raw:
            a = float(raw["bottom"])
            b = float(raw["top"])
        else:
            continue
        lo, hi = sorted((max(min(a, zmax), zmin), max(min(b, zmax), zmin)))
        if hi <= lo:
            continue
        lid = str(raw.get("layer_id") or raw.get("name") or f"layer_{idx + 1}")
        material = str(raw.get("material_id") or lid)
        role = str(raw.get("role") or "soil")
        rows.append(SoilLayerDefinition(lid, lo, hi, material, role, metadata={k: v for k, v in raw.items() if isinstance(k, str)}))
    rows.sort(key=lambda row: row.z_min)
    if not rows:
        rows = (SoilLayerDefinition("soil_layer", zmin, zmax if zmax > zmin else zmin + 1.0, "soil_layer", "soil"),)  # type: ignore[assignment]
    return tuple(rows)


def build_soil_layer_volume_mesh(project_or_mesh: object, *, layers: Iterable[Mapping[str, object]] = (), dims: tuple[int, int] = (1, 1), element_family: str = "hex8", attach: bool = False) -> tuple[MeshDocument | None, SoilLayerCutReport]:
    source_mesh = _current_mesh(project_or_mesh)
    if source_mesh is None:
        return None, SoilLayerCutReport(ok=False, diagnostics=("mesh.missing",))
    bounds = _mesh_bounds(source_mesh)
    layer_defs = normalize_soil_layers(layers, bounds=bounds)
    xmin, xmax, ymin, ymax, _zmin, _zmax = bounds
    nx, ny = max(1, int(dims[0])), max(1, int(dims[1]))
    family = str(element_family or "hex8").lower()
    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    block_ids: list[str] = []
    materials: list[str] = []
    roles: list[str] = []
    region_names: list[str] = []
    interface_candidates: list[dict[str, object]] = []

    node_lookup: dict[tuple[int, int, int], int] = {}

    def add_node(x: float, y: float, z: float) -> int:
        key = (round(float(x) * 1.0e12), round(float(y) * 1.0e12), round(float(z) * 1.0e12))
        if key in node_lookup:
            return node_lookup[key]
        nodes.append((float(x), float(y), float(z)))
        node_lookup[key] = len(nodes) - 1
        return len(nodes) - 1

    previous_layer_id = ""
    for layer in layer_defs:
        layer_node_index: dict[tuple[int, int, int], int] = {}
        for k, z in enumerate((layer.z_min, layer.z_max)):
            for j in range(ny + 1):
                y = ymin + (ymax - ymin if ymax > ymin else 1.0) * j / ny
                for i in range(nx + 1):
                    x = xmin + (xmax - xmin if xmax > xmin else 1.0) * i / nx
                    layer_node_index[(i, j, k)] = add_node(x, y, z)
        def nid(i: int, j: int, k: int) -> int:
            return layer_node_index[(i, j, k)]
        for j in range(ny):
            for i in range(nx):
                hex_nodes = (
                    nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0),
                    nid(i, j, 1), nid(i + 1, j, 1), nid(i + 1, j + 1, 1), nid(i, j + 1, 1),
                )
                if family == "tet4":
                    for tet_idx in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
                        cells.append(tuple(hex_nodes[t] for t in tet_idx))
                        cell_types.append("tet4")
                        block_ids.append(layer.layer_id)
                        materials.append(layer.material_id)
                        roles.append(layer.role)
                        region_names.append(layer.layer_id)
                else:
                    cells.append(hex_nodes)
                    cell_types.append("hex8")
                    block_ids.append(layer.layer_id)
                    materials.append(layer.material_id)
                    roles.append(layer.role)
                    region_names.append(layer.layer_id)
        if previous_layer_id:
            interface_candidates.append({"master_ref": previous_layer_id, "slave_ref": layer.layer_id, "mode": "soil_layer_z_cut", "z": float(layer.z_min)})
        previous_layer_id = layer.layer_id
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags={"block_id": block_ids, "region_name": region_names, "role": roles, "material_id": materials},
        face_tags={"interface_candidates": interface_candidates},
        quality=MeshQualityReport(min_quality=1.0, warnings=[]),
        metadata={
            "source": "geometry_kernel_soil_layer_cut",
            "mesh_kind": "soil_layered_volume_from_stl",
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "complete_3d_mesh": True,
            "solid_solver_ready": True,
            "requires_volume_meshing": False,
            "cell_families": sorted(set(cell_types)),
            "soil_layer_count": len(layer_defs),
            "geometry_kernel": "soil_layer_cut_v1",
            "bounds": list(bounds),
        },
    )
    try:
        apply_3d_boundary_tags(mesh)
    except Exception:
        pass
    report = SoilLayerCutReport(
        ok=bool(mesh.cell_count > 0),
        layer_count=len(layer_defs),
        generated_cell_count=int(mesh.cell_count),
        generated_node_count=int(mesh.node_count),
        material_ids=tuple(sorted(set(materials))),
        interface_candidate_count=len(interface_candidates),
        element_family="tet4" if family == "tet4" else "hex8",
        layers=layer_defs,
        diagnostics=(),
        metadata={"contract_version": "soil_layer_cut_report_v1"},
    )
    mesh.metadata["soil_layer_cut"] = report.to_dict()
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.mesh_settings.element_family = report.element_family
            project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
            project.mesh_model.mesh_settings.metadata["volume_mesher"] = "soil_layered_volume_from_stl"
            project.mesh_model.attach_mesh(mesh)
    return mesh, report


def build_geometry_kernel_report(project_or_mesh: object, *, include_optimization: bool = True) -> GeometryKernelReport:
    optimized = None
    stl_report = None
    if include_optimization:
        optimized, stl_report = optimize_stl_surface_mesh(project_or_mesh, attach=False)
    return GeometryKernelReport(
        ok=bool(stl_report.ok if stl_report is not None else True),
        dependency_status=geometry_kernel_dependency_status(),
        stl_optimization=stl_report,
        metadata={"optimized_mesh_available": optimized is not None, "contract_version": "geometry_kernel_report_v1"},
    )


__all__ = [
    "build_geometry_kernel_report",
    "build_soil_layer_volume_mesh",
    "build_stratigraphic_surface_volume_mesh",
    "geometry_kernel_dependency_status",
    "gmsh_meshio_validation_report",
    "normalize_soil_layers",
    "optimize_complex_stl_surface_mesh",
    "optimize_stl_surface_mesh",
    "optimize_volume_mesh_quality",
]

# ---------------------------------------------------------------------------
# 0.8.76 production STL geometry-kernel hardening
# ---------------------------------------------------------------------------


def _physical_group_records_from_mesh(mesh: MeshDocument | None) -> tuple[GmshPhysicalGroupRecord, ...]:
    if mesh is None:
        return ()
    records: list[GmshPhysicalGroupRecord] = []
    seen: set[tuple[int, str, str]] = set()
    region_tags = list(mesh.cell_tags.get("region_name", []) or mesh.cell_tags.get("block_id", []) or [])
    material_tags = list(mesh.cell_tags.get("material_id", []) or [])
    roles = list(mesh.cell_tags.get("role", []) or [])
    surface_tags = list(mesh.cell_tags.get("surface_id", []) or [])
    for cid in range(int(mesh.cell_count)):
        region = str(region_tags[cid]) if cid < len(region_tags) else "region"
        material = str(material_tags[cid]) if cid < len(material_tags) else ""
        role = str(roles[cid]) if cid < len(roles) else ""
        surface_id = str(surface_tags[cid]) if cid < len(surface_tags) else region
        dim = 2 if str((mesh.cell_types or [""])[cid]).lower() in {"tri3", "quad4"} else 3
        key = (dim, surface_id or region, material)
        if key in seen:
            continue
        seen.add(key)
        count = sum(
            1
            for i in range(int(mesh.cell_count))
            if (str((surface_tags[i] if i < len(surface_tags) else (region_tags[i] if i < len(region_tags) else "region"))) == key[1])
            and (str((material_tags[i] if i < len(material_tags) else "")) == material)
        )
        records.append(GmshPhysicalGroupRecord(name=key[1], dimension=dim, tag=len(records) + 1, material_id=material, role=role, entity_count=count))
    return tuple(records)


def gmsh_meshio_validation_report(project_or_mesh: object) -> GmshMeshioValidationReport:
    """Return optional Gmsh/meshio health plus physical-group preservation plan."""

    mesh = _current_mesh(project_or_mesh)
    status = geometry_kernel_dependency_status()
    diagnostics = list(status.diagnostics)
    physical_groups = _physical_group_records_from_mesh(mesh)
    if not physical_groups:
        diagnostics.append("No region/surface physical groups were inferred from the current mesh tags.")
    if not status.production_tet4_available:
        diagnostics.append("Production Gmsh+meshio Tet4 generation is gated off; fallback meshers preserve physical-group metadata in MeshDocument tags.")
    return GmshMeshioValidationReport(
        ok=bool(status.production_tet4_available or physical_groups),
        dependency_status=status,
        physical_groups=physical_groups,
        diagnostics=tuple(diagnostics),
        metadata={"contract_version": "gmsh_meshio_validation_report_v1", "physical_group_count": len(physical_groups)},
    )


def _boundary_loops(mesh: MeshDocument) -> list[list[int]]:
    counts = _edge_counts(mesh)
    boundary_edges = [edge for edge, count in counts.items() if count == 1]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary_edges:
        adjacency[a].append(b)
        adjacency[b].append(a)
    loops: list[list[int]] = []
    visited: set[tuple[int, int]] = set()
    for start_a, start_b in boundary_edges:
        edge_key = (min(start_a, start_b), max(start_a, start_b))
        if edge_key in visited:
            continue
        loop = [start_a, start_b]
        visited.add(edge_key)
        prev, current = start_a, start_b
        for _ in range(max(4, len(boundary_edges) + 2)):
            neighbours = [n for n in adjacency.get(current, []) if n != prev]
            if not neighbours:
                break
            nxt = neighbours[0]
            edge_key = (min(current, nxt), max(current, nxt))
            if edge_key in visited:
                if nxt == loop[0]:
                    break
                break
            loop.append(nxt)
            visited.add(edge_key)
            prev, current = current, nxt
            if current == loop[0]:
                break
        if len(loop) >= 3:
            if loop[-1] == loop[0]:
                loop = loop[:-1]
            loops.append(loop)
    return loops


def _signed_surface_volume(mesh: MeshDocument) -> float:
    total = 0.0
    for cell, ctype in zip(mesh.cells, mesh.cell_types or ["tri3"] * mesh.cell_count):
        if str(ctype).lower() != "tri3" or len(cell) < 3:
            continue
        a, b, c = (mesh.nodes[int(cell[0])], mesh.nodes[int(cell[1])], mesh.nodes[int(cell[2])])
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
        total += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
    return total


def _triangle_aabb(mesh: MeshDocument, cell: Sequence[int]) -> tuple[float, float, float, float, float, float]:
    pts = [mesh.nodes[int(i)] for i in cell[:3]]
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    zs = [float(p[2]) for p in pts]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _self_intersection_candidates(mesh: MeshDocument, *, limit: int = 10000) -> int:
    tri_ids = [i for i, ctype in enumerate(mesh.cell_types or []) if str(ctype).lower() == "tri3"]
    count = 0
    boxes: dict[int, tuple[float, float, float, float, float, float]] = {i: _triangle_aabb(mesh, mesh.cells[i]) for i in tri_ids}
    for pos, i in enumerate(tri_ids):
        ai = boxes[i]
        nodes_i = set(int(v) for v in mesh.cells[i][:3])
        for j in tri_ids[pos + 1:]:
            if nodes_i.intersection(int(v) for v in mesh.cells[j][:3]):
                continue
            bj = boxes[j]
            if ai[1] < bj[0] or bj[1] < ai[0] or ai[3] < bj[2] or bj[3] < ai[2] or ai[5] < bj[4] or bj[5] < ai[4]:
                continue
            count += 1
            if count >= limit:
                return count
    return count


def optimize_complex_stl_surface_mesh(
    project_or_mesh: object,
    *,
    tolerance: float = 1.0e-9,
    fill_holes: bool = True,
    max_hole_edges: int = 64,
    orient_normals: bool = True,
    detect_self_intersections: bool = True,
    attach: bool = False,
) -> tuple[MeshDocument | None, STLOptimizationReport]:
    """Repair complex STL shells with deterministic dependency-light operations.

    This function is intentionally conservative.  It removes duplicate nodes and
    degenerate triangles, can cap small boundary loops with fan patches, flips a
    consistently inward closed shell, and reports self-intersection *candidates*
    via triangle AABB overlap diagnostics.  It does not claim CAD-grade Boolean
    repair; when optional Gmsh/meshio is present, callers can use the same report
    as a pre-flight gate for production conformal meshing.
    """

    optimized, base = optimize_stl_surface_mesh(project_or_mesh, tolerance=tolerance, attach=False)
    if optimized is None:
        return None, base
    actions = list(base.actions)
    filled_faces = 0
    filled_loops = 0
    if fill_holes:
        loops = _boundary_loops(optimized)
        for loop in loops:
            if len(loop) < 3 or len(loop) > int(max_hole_edges):
                continue
            cx = sum(float(optimized.nodes[i][0]) for i in loop) / len(loop)
            cy = sum(float(optimized.nodes[i][1]) for i in loop) / len(loop)
            cz = sum(float(optimized.nodes[i][2]) for i in loop) / len(loop)
            center_id = len(optimized.nodes)
            optimized.nodes.append((cx, cy, cz))
            for idx, a in enumerate(loop):
                b = loop[(idx + 1) % len(loop)]
                optimized.cells.append((int(a), int(b), center_id))
                optimized.cell_types.append("tri3")
                filled_faces += 1
            filled_loops += 1
        if filled_faces:
            # Extend cell tags for new patch faces.
            for key, values in list(optimized.cell_tags.items()):
                default = "stl_hole_patch" if key in {"block_id", "region_name", "surface_id"} else ("geology_surface" if key == "role" else (values[-1] if values else ""))
                optimized.cell_tags[key] = list(values) + [default] * filled_faces
            if "role" not in optimized.cell_tags:
                optimized.cell_tags["role"] = ["geology_surface"] * (len(optimized.cells) - filled_faces) + ["stl_hole_patch"] * filled_faces
            actions.append(STLOptimizationAction("stl.holes_patched", "Patched small open STL boundary loops with deterministic fan triangles.", "warning", filled_faces, metadata={"loop_count": filled_loops}))
    flipped = 0
    if orient_normals:
        open_edges, nonmanifold, tri_count, closed, manifold = _stl_counts(optimized)
        signed_volume = _signed_surface_volume(optimized)
        if closed and manifold and signed_volume < 0.0:
            new_cells: list[tuple[int, ...]] = []
            for cell, ctype in zip(optimized.cells, optimized.cell_types or []):
                if str(ctype).lower() == "tri3" and len(cell) >= 3:
                    new_cells.append((int(cell[0]), int(cell[2]), int(cell[1])))
                    flipped += 1
                else:
                    new_cells.append(tuple(int(v) for v in cell))
            optimized.cells = new_cells
            actions.append(STLOptimizationAction("stl.normals_reoriented", "Reoriented inward STL triangle winding to outward shell volume.", "warning", flipped))
    self_candidates = _self_intersection_candidates(optimized) if detect_self_intersections else 0
    if self_candidates:
        actions.append(STLOptimizationAction("stl.self_intersection_candidates", "Detected triangle AABB self-intersection candidates; use CAD/Gmsh repair for exact resolution.", "warning", self_candidates))
    open_edges, nonmanifold, _tri_count, closed, manifold = _stl_counts(optimized)
    report = STLOptimizationReport(
        ok=bool(not open_edges and not nonmanifold and int(optimized.cell_count) > 0),
        original_node_count=base.original_node_count,
        optimized_node_count=int(optimized.node_count),
        original_face_count=base.original_face_count,
        optimized_face_count=int(optimized.cell_count),
        duplicate_node_count=base.duplicate_node_count,
        degenerate_face_count=base.degenerate_face_count,
        open_boundary_edge_count=open_edges,
        nonmanifold_edge_count=nonmanifold,
        closed=closed,
        manifold=manifold,
        actions=tuple(actions),
        metadata={
            "contract_version": "stl_optimization_report_v2",
            "filled_hole_face_count": filled_faces,
            "filled_hole_loop_count": filled_loops,
            "flipped_normal_face_count": flipped,
            "self_intersection_candidate_count": self_candidates,
            "repair_profile": "complex_stl_dependency_light",
        },
    )
    optimized.metadata["stl_optimization"] = report.to_dict()
    optimized.metadata["geometry_kernel_complex_repair"] = True
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.attach_mesh(optimized)
    return optimized, report


def _surface_node_ids(mesh: MeshDocument, surface_id: str) -> list[int]:
    target = str(surface_id)
    keys = ("surface_id", "region_name", "block_id", "role")
    ids: set[int] = set()
    for cid, cell in enumerate(mesh.cells):
        matched = False
        for key in keys:
            values = list(mesh.cell_tags.get(key, []) or [])
            if cid < len(values) and str(values[cid]) == target:
                matched = True
                break
        if matched:
            ids.update(int(v) for v in cell)
    return sorted(ids)


def _surface_samples(mesh: MeshDocument, surface_id: str) -> list[tuple[float, float, float]]:
    node_ids = _surface_node_ids(mesh, surface_id)
    if not node_ids and surface_id in {"all", "*", ""}:
        node_ids = list(range(mesh.node_count))
    return [(float(mesh.nodes[i][0]), float(mesh.nodes[i][1]), float(mesh.nodes[i][2])) for i in node_ids]


def _interpolate_z(samples: Sequence[tuple[float, float, float]], x: float, y: float, fallback: float) -> float:
    if not samples:
        return float(fallback)
    weighted = 0.0
    weights = 0.0
    for sx, sy, sz in samples:
        d2 = (sx - x) * (sx - x) + (sy - y) * (sy - y)
        if d2 <= 1.0e-18:
            return float(sz)
        w = 1.0 / max(d2, 1.0e-18)
        weighted += w * float(sz)
        weights += w
    return float(weighted / weights) if weights else float(fallback)


def _normalize_surface_layers(layers: Iterable[Mapping[str, object]]) -> tuple[SurfaceStratigraphyDefinition, ...]:
    rows: list[SurfaceStratigraphyDefinition] = []
    for idx, raw in enumerate(layers):
        top = str(raw.get("top_surface_id") or raw.get("top_surface") or raw.get("top") or "")
        bottom = str(raw.get("bottom_surface_id") or raw.get("bottom_surface") or raw.get("bottom") or "")
        if not top or not bottom:
            continue
        lid = str(raw.get("layer_id") or raw.get("name") or f"stratum_{idx + 1}")
        material = str(raw.get("material_id") or lid)
        role = str(raw.get("role") or "soil")
        rows.append(SurfaceStratigraphyDefinition(lid, top, bottom, material, role, metadata={k: v for k, v in raw.items() if isinstance(k, str)}))
    return tuple(rows)


def build_stratigraphic_surface_volume_mesh(
    project_or_mesh: object,
    *,
    layers: Iterable[Mapping[str, object]] = (),
    dims: tuple[int, int] = (1, 1),
    element_family: str = "hex8",
    attach: bool = False,
) -> tuple[MeshDocument | None, StratigraphicClosureReport]:
    """Build sealed volumes between real imported stratigraphic surfaces.

    The fallback kernel samples each named surface by inverse-distance z(x, y)
    interpolation and creates conforming Hex8/Tet4 layers over a shared XY grid.
    Gmsh/meshio installations can use the same metadata/physical groups as a
    hand-off contract for future CAD-grade Boolean/fragment meshing.
    """

    source_mesh = _current_mesh(project_or_mesh)
    if source_mesh is None:
        return None, StratigraphicClosureReport(ok=False, diagnostics=("mesh.missing",))
    bounds = _mesh_bounds(source_mesh)
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    layer_defs = _normalize_surface_layers(layers)
    if not layer_defs:
        return None, StratigraphicClosureReport(ok=False, diagnostics=("stratigraphy.layers_missing",))
    nx, ny = max(1, int(dims[0])), max(1, int(dims[1]))
    family = str(element_family or "hex8").lower()
    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    block_ids: list[str] = []
    materials: list[str] = []
    roles: list[str] = []
    region_names: list[str] = []
    node_lookup: dict[tuple[int, int, int], int] = {}
    diagnostics: list[str] = []
    interface_candidates: list[dict[str, object]] = []

    def add_node(x: float, y: float, z: float) -> int:
        key = (round(float(x) * 1.0e10), round(float(y) * 1.0e10), round(float(z) * 1.0e10))
        if key in node_lookup:
            return node_lookup[key]
        nodes.append((float(x), float(y), float(z)))
        node_lookup[key] = len(nodes) - 1
        return len(nodes) - 1

    previous_layer_id = ""
    used_surfaces: set[str] = set()
    for layer in layer_defs:
        top_samples = _surface_samples(source_mesh, layer.top_surface_id)
        bottom_samples = _surface_samples(source_mesh, layer.bottom_surface_id)
        used_surfaces.update({layer.top_surface_id, layer.bottom_surface_id})
        if not top_samples:
            diagnostics.append(f"surface.missing:{layer.top_surface_id}")
        if not bottom_samples:
            diagnostics.append(f"surface.missing:{layer.bottom_surface_id}")
        layer_node_index: dict[tuple[int, int, int], int] = {}
        valid_layer = True
        for j in range(ny + 1):
            y = ymin + (ymax - ymin if ymax > ymin else 1.0) * j / ny
            for i in range(nx + 1):
                x = xmin + (xmax - xmin if xmax > xmin else 1.0) * i / nx
                zb = _interpolate_z(bottom_samples, x, y, zmin)
                zt = _interpolate_z(top_samples, x, y, zmax)
                if zt <= zb:
                    zt, zb = max(zt, zb), min(zt, zb)
                if zt - zb <= 1.0e-12:
                    valid_layer = False
                layer_node_index[(i, j, 0)] = add_node(x, y, zb)
                layer_node_index[(i, j, 1)] = add_node(x, y, zt)
        if not valid_layer:
            diagnostics.append(f"stratigraphy.zero_thickness:{layer.layer_id}")
            continue
        def nid(i: int, j: int, k: int) -> int:
            return layer_node_index[(i, j, k)]
        for j in range(ny):
            for i in range(nx):
                hex_nodes = (
                    nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0),
                    nid(i, j, 1), nid(i + 1, j, 1), nid(i + 1, j + 1, 1), nid(i, j + 1, 1),
                )
                if family == "tet4":
                    for tet_idx in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
                        cells.append(tuple(hex_nodes[t] for t in tet_idx))
                        cell_types.append("tet4")
                        block_ids.append(layer.layer_id)
                        materials.append(layer.material_id)
                        roles.append(layer.role)
                        region_names.append(layer.layer_id)
                else:
                    cells.append(hex_nodes)
                    cell_types.append("hex8")
                    block_ids.append(layer.layer_id)
                    materials.append(layer.material_id)
                    roles.append(layer.role)
                    region_names.append(layer.layer_id)
        if previous_layer_id:
            interface_candidates.append({"master_ref": previous_layer_id, "slave_ref": layer.layer_id, "mode": "stratigraphic_surface_closure", "surface_id": layer.bottom_surface_id})
        previous_layer_id = layer.layer_id
    physical_groups = tuple(
        GmshPhysicalGroupRecord(name=layer.layer_id, dimension=3, tag=idx + 1, material_id=layer.material_id, role=layer.role, entity_count=block_ids.count(layer.layer_id))
        for idx, layer in enumerate(layer_defs)
    )
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags={"block_id": block_ids, "region_name": region_names, "role": roles, "material_id": materials},
        face_tags={"interface_candidates": interface_candidates},
        quality=MeshQualityReport(min_quality=1.0 if cells else 0.0, warnings=list(diagnostics)),
        metadata={
            "source": "geometry_kernel_stratigraphic_surface_closure",
            "mesh_kind": "stratigraphic_surface_volume_from_stl",
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "complete_3d_mesh": True,
            "solid_solver_ready": bool(cells),
            "requires_volume_meshing": False,
            "cell_families": sorted(set(cell_types)),
            "geometry_kernel": "stratigraphic_surface_closure_v1",
            "bounds": list(bounds),
            "surface_ids": sorted(used_surfaces),
            "gmsh_physical_groups": [row.to_dict() for row in physical_groups],
        },
    )
    try:
        apply_3d_boundary_tags(mesh)
    except Exception:
        pass
    report = StratigraphicClosureReport(
        ok=bool(cells and not any(item.startswith("surface.missing") or item.startswith("stratigraphy.zero_thickness") for item in diagnostics)),
        layer_count=len(layer_defs),
        generated_cell_count=int(mesh.cell_count),
        generated_node_count=int(mesh.node_count),
        material_ids=tuple(sorted(set(materials))),
        surface_ids=tuple(sorted(used_surfaces)),
        interface_candidate_count=len(interface_candidates),
        element_family="tet4" if family == "tet4" else "hex8",
        layers=layer_defs,
        physical_groups=physical_groups,
        diagnostics=tuple(diagnostics),
        metadata={"contract_version": "stratigraphic_closure_report_v1"},
    )
    mesh.metadata["stratigraphic_closure"] = report.to_dict()
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.mesh_settings.element_family = report.element_family
            project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = bool(report.ok)
            project.mesh_model.mesh_settings.metadata["volume_mesher"] = "stratigraphic_surface_volume_from_stl"
            project.mesh_model.mesh_settings.metadata["physical_group_preservation"] = True
            project.mesh_model.attach_mesh(mesh)
    return mesh, report


def _cell_measure(mesh: MeshDocument, cell: Sequence[int], ctype: str) -> float:
    if str(ctype).lower() == "tet4" and len(cell) >= 4:
        a, b, c, d = [mesh.nodes[int(i)] for i in cell[:4]]
        ax, ay, az = [float(v) for v in a]
        bx, by, bz = [float(v) for v in b]
        cx, cy, cz = [float(v) for v in c]
        dx, dy, dz = [float(v) for v in d]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        wx, wy, wz = dx - ax, dy - ay, dz - az
        return abs(ux * (vy * wz - vz * wy) - uy * (vx * wz - vz * wx) + uz * (vx * wy - vy * wx)) / 6.0
    if str(ctype).lower() == "hex8" and len(cell) >= 8:
        pts = [mesh.nodes[int(i)] for i in cell[:8]]
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        zs = [float(p[2]) for p in pts]
        return abs((max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs)))
    return 1.0


def _cell_aspect(mesh: MeshDocument, cell: Sequence[int]) -> float:
    pts = [mesh.nodes[int(i)] for i in cell]
    lengths: list[float] = []
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            lengths.append(math.dist((float(p[0]), float(p[1]), float(p[2])), (float(q[0]), float(q[1]), float(q[2]))))
    positive = [v for v in lengths if v > 1.0e-15]
    if not positive:
        return float("inf")
    return max(positive) / min(positive)


def optimize_volume_mesh_quality(project_or_mesh: object, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 1.0e6, attach: bool = False) -> tuple[MeshDocument | None, MeshQualityOptimizationReport]:
    mesh = _current_mesh(project_or_mesh)
    if mesh is None:
        return None, MeshQualityOptimizationReport(ok=False, actions=("mesh.missing",))
    volumes = [_cell_measure(mesh, cell, ctype) for cell, ctype in zip(mesh.cells, mesh.cell_types or [])]
    aspects = [_cell_aspect(mesh, cell) for cell in mesh.cells]
    bad = [idx for idx, (vol, asp) in enumerate(zip(volumes, aspects)) if vol <= float(min_volume) or asp > float(max_aspect_ratio)]
    keep = [idx for idx in range(mesh.cell_count) if idx not in set(bad)]
    if not bad:
        report = MeshQualityOptimizationReport(
            ok=True,
            original_cell_count=int(mesh.cell_count),
            optimized_cell_count=int(mesh.cell_count),
            min_volume_before=min(volumes) if volumes else None,
            min_volume_after=min(volumes) if volumes else None,
            max_aspect_ratio_before=max(aspects) if aspects else None,
            max_aspect_ratio_after=max(aspects) if aspects else None,
            actions=("mesh.quality_no_bad_cells",),
            metadata={"contract_version": "mesh_quality_optimization_report_v1"},
        )
        mesh.metadata["mesh_quality_optimization"] = report.to_dict()
        return mesh, report
    new_tags: dict[str, list[Any]] = {}
    for key, values in mesh.cell_tags.items():
        vals = list(values)
        new_tags[key] = [vals[i] if i < len(vals) else "" for i in keep]
    optimized = MeshDocument(
        nodes=list(mesh.nodes),
        cells=[tuple(mesh.cells[i]) for i in keep],
        cell_types=[str(mesh.cell_types[i]) for i in keep],
        cell_tags=new_tags,
        face_tags=dict(mesh.face_tags),
        node_tags=dict(mesh.node_tags),
        quality=MeshQualityReport(
            min_quality=1.0 if keep else 0.0,
            max_aspect_ratio=max([aspects[i] for i in keep], default=None),
            bad_cell_ids=[],
            warnings=[f"Removed {len(bad)} bad volume cell(s) during local quality optimization."],
        ),
        metadata={**dict(mesh.metadata), "mesh_quality_optimized": True},
    )
    try:
        apply_3d_boundary_tags(optimized)
    except Exception:
        pass
    after_vol = [_cell_measure(optimized, cell, ctype) for cell, ctype in zip(optimized.cells, optimized.cell_types or [])]
    after_asp = [_cell_aspect(optimized, cell) for cell in optimized.cells]
    report = MeshQualityOptimizationReport(
        ok=bool(optimized.cell_count > 0),
        original_cell_count=int(mesh.cell_count),
        optimized_cell_count=int(optimized.cell_count),
        removed_bad_cell_count=len(bad),
        min_volume_before=min(volumes) if volumes else None,
        min_volume_after=min(after_vol) if after_vol else None,
        max_aspect_ratio_before=max(aspects) if aspects else None,
        max_aspect_ratio_after=max(after_asp) if after_asp else None,
        bad_cell_ids=tuple(int(i) for i in bad),
        actions=("mesh.bad_cells_removed",),
        metadata={"contract_version": "mesh_quality_optimization_report_v1"},
    )
    optimized.metadata["mesh_quality_optimization"] = report.to_dict()
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.attach_mesh(optimized)
    return optimized, report

# ---------------------------------------------------------------------------
# 0.8.77 production Gmsh/OCC validation, local remeshing and diagnostics logs
# ---------------------------------------------------------------------------


def geometry_operation_log_status() -> dict[str, object]:
    """Return current geometry-kernel debug logging status."""

    return _geometry_log_status()


def _state_summary(mesh: MeshDocument | None) -> dict[str, object]:
    if mesh is None:
        return {"has_mesh": False}
    return {
        "has_mesh": True,
        "node_count": int(mesh.node_count),
        "cell_count": int(mesh.cell_count),
        "cell_families": sorted(set(str(item).lower() for item in mesh.cell_types)),
        "mesh_role": str(mesh.metadata.get("mesh_role", "")),
        "mesh_kind": str(mesh.metadata.get("mesh_kind", "")),
    }


def _write_ascii_stl(mesh: MeshDocument, path: str, *, name: str = "geoai_stl") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"solid {name}\n")
        for cid, cell in enumerate(mesh.cells):
            ctype = str((mesh.cell_types or [""] * mesh.cell_count)[cid]).lower()
            if ctype != "tri3" or len(cell) < 3:
                continue
            a, b, c = [mesh.nodes[int(i)] for i in cell[:3]]
            ax, ay, az = float(a[0]), float(a[1]), float(a[2])
            bx, by, bz = float(b[0]), float(b[1]), float(b[2])
            cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            norm = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / norm, ny / norm, nz / norm
            fh.write(f"  facet normal {nx:.17g} {ny:.17g} {nz:.17g}\n")
            fh.write("    outer loop\n")
            for p in (a, b, c):
                fh.write(f"      vertex {float(p[0]):.17g} {float(p[1]):.17g} {float(p[2]):.17g}\n")
            fh.write("    endloop\n  endfacet\n")
        fh.write(f"endsolid {name}\n")


def _meshdocument_from_meshio(meshio_mesh: object, *, physical_tag_map: Mapping[int, GmshPhysicalGroupRecord] | None = None) -> MeshDocument:
    points = getattr(meshio_mesh, "points")
    nodes = [(float(row[0]), float(row[1]), float(row[2] if len(row) > 2 else 0.0)) for row in points]
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    material_ids: list[str] = []
    region_names: list[str] = []
    block_ids: list[str] = []
    roles: list[str] = []
    physical_ids: list[int] = []
    tag_map = dict(physical_tag_map or {})
    cell_data_dict = getattr(meshio_mesh, "cell_data_dict", {}) or {}
    physical_by_type = cell_data_dict.get("gmsh:physical", {}) if isinstance(cell_data_dict, Mapping) else {}
    for cell_block in getattr(meshio_mesh, "cells", []):
        block_type = str(getattr(cell_block, "type", "")).lower()
        if block_type not in {"tetra", "tetra4", "tet4", "hexahedron", "hex8"}:
            continue
        ctype = "hex8" if block_type in {"hexahedron", "hex8"} else "tet4"
        data = getattr(cell_block, "data", [])
        phys_values = list(physical_by_type.get(block_type, [])) if isinstance(physical_by_type, Mapping) else []
        for idx, row in enumerate(data):
            cell = tuple(int(v) for v in list(row)[: (8 if ctype == "hex8" else 4)])
            tag = int(phys_values[idx]) if idx < len(phys_values) else 0
            record = tag_map.get(tag)
            region = record.name if record is not None else (f"physical_{tag}" if tag else "gmsh_volume")
            material = record.material_id if record is not None and record.material_id else region
            role = record.role if record is not None and record.role else "solid"
            cells.append(cell)
            cell_types.append(ctype)
            physical_ids.append(tag)
            region_names.append(region)
            block_ids.append(region)
            material_ids.append(material)
            roles.append(role)
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags={
            "block_id": block_ids,
            "region_name": region_names,
            "material_id": material_ids,
            "role": roles,
            "gmsh_physical_id": physical_ids,
        },
        face_tags={},
        quality=MeshQualityReport(min_quality=1.0 if cells else 0.0, warnings=[] if cells else ["No tetra/hex volume cells were read from meshio output."]),
        metadata={
            "source": "gmsh_occ_fragment_meshio",
            "mesh_kind": "gmsh_occ_fragment_tet4_from_stl",
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "solid_solver_ready": bool(cells),
            "complete_3d_mesh": True,
            "requires_volume_meshing": False,
            "cell_families": sorted(set(cell_types)),
        },
    )
    try:
        apply_3d_boundary_tags(mesh)
    except Exception:
        pass
    return mesh


def build_gmsh_occ_fragment_tet4_mesh(
    project_or_mesh: object,
    *,
    layers: Iterable[Mapping[str, object]] = (),
    mesh_size: float | None = None,
    attach: bool = False,
    allow_fallback: bool = True,
    debug: bool | None = None,
    debug_dir: str | None = None,
) -> tuple[MeshDocument | None, GmshOCCFragmentMeshingReport]:
    """Generate a production Tet4 mesh through Gmsh/OCC when available.

    In installed Gmsh/meshio environments this function creates OCC layer boxes
    from the current STL bounds, fragments them, assigns physical volumes, runs
    3D meshing and converts the ``.msh`` result to :class:`MeshDocument`.  When
    optional dependencies are unavailable or Gmsh fails, the report records the
    exact failure and, if ``allow_fallback`` is true, produces the deterministic
    stratigraphic fallback mesh used by earlier geometry-kernel versions.
    """

    import os
    import tempfile
    import time

    start_counter = time.perf_counter()
    started_at = ""
    try:
        from datetime import datetime, timezone
        started_at = datetime.now(timezone.utc).isoformat()
    except Exception:
        started_at = ""
    source_mesh = _current_mesh(project_or_mesh)
    status = geometry_kernel_dependency_status()
    input_state = {"mesh": _state_summary(source_mesh), "layer_count": len(tuple(layers or ())), "mesh_size": mesh_size or 0.0}
    diagnostics = list(status.diagnostics)
    debug_files: list[str] = []
    physical_groups = _physical_group_records_from_mesh(source_mesh)
    if source_mesh is None:
        report = GmshOCCFragmentMeshingReport(ok=False, dependency_status=status, diagnostics=("mesh.missing",), physical_groups=physical_groups)
        log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="error", diagnostics=report.diagnostics, start_counter=start_counter, started_at=started_at)
        return None, report
    layer_defs = tuple(layers or ())
    if not layer_defs:
        bounds = _mesh_bounds(source_mesh)
        layer_defs = ({"layer_id": "gmsh_volume", "z_min": bounds[4], "z_max": bounds[5], "material_id": "gmsh_volume"},)
    if not status.production_tet4_available:
        diagnostics.append("gmsh_occ_fragment.unavailable: install gmsh and meshio to run production OCC fragment meshing.")
        fallback_mesh = None
        if allow_fallback:
            fallback_mesh, fallback_report = build_soil_layer_volume_mesh(project_or_mesh, layers=layer_defs, dims=(1, 1), element_family="tet4", attach=attach)
            diagnostics.append("gmsh_occ_fragment.fallback_used: dependency-light Tet4 soil-layer mesh generated instead of Gmsh OCC mesh.")
            report = GmshOCCFragmentMeshingReport(
                ok=bool(fallback_mesh is not None and fallback_mesh.cell_count > 0),
                dependency_status=status,
                occ_fragment_attempted=False,
                occ_fragment_used=False,
                meshio_conversion_used=False,
                generated_node_count=int(fallback_mesh.node_count if fallback_mesh is not None else 0),
                generated_cell_count=int(fallback_mesh.cell_count if fallback_mesh is not None else 0),
                physical_groups=physical_groups,
                diagnostics=tuple(diagnostics),
                debug_files=(),
                metadata={"contract_version": "gmsh_occ_fragment_meshing_report_v1", "fallback_report": fallback_report.to_dict() if fallback_mesh is not None else {}},
            )
            if fallback_mesh is not None:
                fallback_mesh.metadata["gmsh_occ_fragment"] = report.to_dict()
            log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="fallback", diagnostics=report.diagnostics, start_counter=start_counter, started_at=started_at)
            return fallback_mesh, report
        report = GmshOCCFragmentMeshingReport(ok=False, dependency_status=status, diagnostics=tuple(diagnostics), physical_groups=physical_groups)
        log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="unavailable", diagnostics=report.diagnostics, start_counter=start_counter, started_at=started_at)
        return None, report
    try:
        import gmsh  # type: ignore[import-not-found]
        import meshio  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - only hit in optional dependency edge cases
        diagnostics.append(f"gmsh_occ_fragment.import_error:{type(exc).__name__}:{exc}")
        report = GmshOCCFragmentMeshingReport(ok=False, dependency_status=status, diagnostics=tuple(diagnostics), physical_groups=physical_groups)
        log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="error", diagnostics=report.diagnostics, error=str(exc), start_counter=start_counter, started_at=started_at)
        return None, report
    tmpdir_obj = tempfile.TemporaryDirectory(prefix="geoai_gmsh_occ_")
    tmpdir = tmpdir_obj.name
    msh_path = os.path.join(tmpdir, "fragmented_strata.msh")
    debug_keep_dir = debug_dir or os.getenv("GEOAI_SIMKIT_GEOMETRY_LOG_DIR") or ""
    try:  # pragma: no cover - exercised on machines with gmsh/meshio installed
        gmsh.initialize()
        gmsh.model.add("geoai_stratigraphic_occ_fragment")
        xmin, xmax, ymin, ymax, zmin, zmax = _mesh_bounds(source_mesh)
        normalized = normalize_soil_layers(layer_defs, bounds=(xmin, xmax, ymin, ymax, zmin, zmax))
        volume_entities: list[tuple[int, int]] = []
        physical_records: list[GmshPhysicalGroupRecord] = []
        for idx, layer in enumerate(normalized):
            tag = gmsh.model.occ.addBox(float(xmin), float(ymin), float(layer.z_min), float(xmax - xmin or 1.0), float(ymax - ymin or 1.0), float(layer.z_max - layer.z_min or 1.0))
            volume_entities.append((3, tag))
            physical_records.append(GmshPhysicalGroupRecord(name=layer.layer_id, dimension=3, tag=idx + 1, material_id=layer.material_id, role=layer.role, entity_count=1, metadata={"source": "occ_layer_volume"}))
        fragmented, _ = gmsh.model.occ.fragment(volume_entities, [])
        gmsh.model.occ.synchronize()
        final_volumes = [ent for ent in gmsh.model.getEntities(3)] or [ent for ent in fragmented if int(ent[0]) == 3]
        tag_map: dict[int, GmshPhysicalGroupRecord] = {}
        for idx, ent in enumerate(final_volumes):
            record = physical_records[min(idx, len(physical_records) - 1)] if physical_records else GmshPhysicalGroupRecord("gmsh_volume", 3, idx + 1, "gmsh_volume", "solid", 1)
            phys_tag = int(record.tag or (idx + 1))
            gmsh.model.addPhysicalGroup(3, [int(ent[1])], phys_tag)
            gmsh.model.setPhysicalName(3, phys_tag, record.name)
            tag_map[phys_tag] = record
        if mesh_size and float(mesh_size) > 0.0:
            gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(mesh_size))
            gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(mesh_size))
        gmsh.model.mesh.generate(3)
        gmsh.write(msh_path)
        debug_files.append(msh_path)
        meshio_mesh = meshio.read(msh_path)
        mesh = _meshdocument_from_meshio(meshio_mesh, physical_tag_map=tag_map)
        mesh.metadata["gmsh_physical_groups"] = [record.to_dict() for record in tag_map.values()]
        mesh.metadata["gmsh_occ_fragment"] = True
        if debug_keep_dir:
            os.makedirs(debug_keep_dir, exist_ok=True)
            kept = os.path.join(debug_keep_dir, "geoai_gmsh_occ_fragmented_strata.msh")
            try:
                shutil.copyfile(msh_path, kept)
                debug_files.append(kept)
            except Exception:
                pass
        if attach and not isinstance(project_or_mesh, MeshDocument):
            project = as_project_context(project_or_mesh).get_project()
            if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
                project.mesh_model.mesh_settings.element_family = "tet4"
                project.mesh_model.mesh_settings.metadata["solid_solver_ready"] = True
                project.mesh_model.mesh_settings.metadata["volume_mesher"] = "gmsh_occ_fragment_tet4_from_stl"
                project.mesh_model.attach_mesh(mesh)
        report = GmshOCCFragmentMeshingReport(
            ok=bool(mesh.cell_count > 0),
            dependency_status=status,
            occ_fragment_attempted=True,
            occ_fragment_used=True,
            meshio_conversion_used=True,
            generated_node_count=int(mesh.node_count),
            generated_cell_count=int(mesh.cell_count),
            physical_groups=tuple(tag_map.values()),
            diagnostics=tuple(diagnostics),
            debug_files=tuple(debug_files),
            metadata={"contract_version": "gmsh_occ_fragment_meshing_report_v1", "strategy": "occ_fragment_layer_boxes_from_stl_bounds"},
        )
        mesh.metadata["gmsh_occ_fragment_report"] = report.to_dict()
        log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="ok", diagnostics=report.diagnostics, debug_files=tuple(debug_files), start_counter=start_counter, started_at=started_at)
        return mesh, report
    except Exception as exc:  # pragma: no cover - only hit with optional Gmsh installed
        diagnostics.append(f"gmsh_occ_fragment.failed:{type(exc).__name__}:{exc}")
        fallback_mesh = None
        if allow_fallback:
            fallback_mesh, fallback_report = build_soil_layer_volume_mesh(project_or_mesh, layers=layer_defs, dims=(1, 1), element_family="tet4", attach=attach)
            diagnostics.append("gmsh_occ_fragment.fallback_used_after_error")
            report = GmshOCCFragmentMeshingReport(
                ok=bool(fallback_mesh is not None and fallback_mesh.cell_count > 0),
                dependency_status=status,
                occ_fragment_attempted=True,
                occ_fragment_used=False,
                meshio_conversion_used=False,
                generated_node_count=int(fallback_mesh.node_count if fallback_mesh is not None else 0),
                generated_cell_count=int(fallback_mesh.cell_count if fallback_mesh is not None else 0),
                physical_groups=physical_groups,
                diagnostics=tuple(diagnostics),
                debug_files=tuple(debug_files),
                metadata={"contract_version": "gmsh_occ_fragment_meshing_report_v1", "fallback_report": fallback_report.to_dict() if fallback_mesh is not None else {}},
            )
            log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="fallback_error", diagnostics=report.diagnostics, error=str(exc), debug_files=tuple(debug_files), start_counter=start_counter, started_at=started_at)
            return fallback_mesh, report
        report = GmshOCCFragmentMeshingReport(ok=False, dependency_status=status, occ_fragment_attempted=True, diagnostics=tuple(diagnostics), physical_groups=physical_groups, debug_files=tuple(debug_files))
        log_geometry_operation("gmsh_occ_fragment_tet4", enabled=debug, debug_dir=debug_dir, input_state=input_state, output_state=report.to_dict(), status="error", diagnostics=report.diagnostics, error=str(exc), debug_files=tuple(debug_files), start_counter=start_counter, started_at=started_at)
        return None, report
    finally:
        try:
            gmsh.finalize()  # type: ignore[name-defined]
        except Exception:
            pass
        if not debug_keep_dir:
            tmpdir_obj.cleanup()


def _subdivide_tet4_with_centroid(mesh: MeshDocument, cell: Sequence[int]) -> tuple[tuple[int, int, int, int], ...]:
    a, b, c, d = [int(v) for v in cell[:4]]
    pts = [mesh.nodes[i] for i in (a, b, c, d)]
    centroid = (sum(float(p[0]) for p in pts) / 4.0, sum(float(p[1]) for p in pts) / 4.0, sum(float(p[2]) for p in pts) / 4.0)
    cid = len(mesh.nodes)
    mesh.nodes.append(centroid)
    return ((a, b, c, cid), (a, b, cid, d), (a, cid, c, d), (cid, b, c, d))


def _split_hex8_to_tets(cell: Sequence[int]) -> tuple[tuple[int, int, int, int], ...]:
    h = tuple(int(v) for v in cell[:8])
    patterns = ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7))
    return tuple(tuple(h[i] for i in pattern) for pattern in patterns)


def local_remesh_volume_mesh_quality(
    project_or_mesh: object,
    *,
    min_volume: float = 1.0e-12,
    max_aspect_ratio: float = 1.0e6,
    attach: bool = False,
    debug: bool | None = None,
    debug_dir: str | None = None,
) -> tuple[MeshDocument | None, LocalRemeshReport]:
    """Replace bad Tet4/Hex8 cells with local sub-cells instead of only filtering."""

    import time
    from datetime import datetime, timezone

    start_counter = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    mesh = _current_mesh(project_or_mesh)
    if mesh is None:
        report = LocalRemeshReport(ok=False, diagnostics=("mesh.missing",))
        log_geometry_operation("local_volume_remesh", enabled=debug, debug_dir=debug_dir, input_state={"has_mesh": False}, output_state=report.to_dict(), status="error", diagnostics=report.diagnostics, start_counter=start_counter, started_at=started_at)
        return None, report
    volumes = [_cell_measure(mesh, cell, ctype) for cell, ctype in zip(mesh.cells, mesh.cell_types or [])]
    aspects = [_cell_aspect(mesh, cell) for cell in mesh.cells]
    bad = [idx for idx, (vol, asp) in enumerate(zip(volumes, aspects)) if vol <= float(min_volume) or asp > float(max_aspect_ratio)]
    if not bad:
        report = LocalRemeshReport(ok=True, original_cell_count=int(mesh.cell_count), final_cell_count=int(mesh.cell_count), actions=("mesh.local_remesh_no_bad_cells",))
        mesh.metadata["local_remesh"] = report.to_dict()
        log_geometry_operation("local_volume_remesh", enabled=debug, debug_dir=debug_dir, input_state=_state_summary(mesh), output_state=report.to_dict(), status="ok", diagnostics=(), start_counter=start_counter, started_at=started_at)
        return mesh, report
    working = MeshDocument(
        nodes=list(mesh.nodes),
        cells=[],
        cell_types=[],
        cell_tags={},
        face_tags=dict(mesh.face_tags),
        node_tags=dict(mesh.node_tags),
        quality=MeshQualityReport(),
        metadata={**dict(mesh.metadata), "mesh_quality_optimized": True, "local_remesh_enabled": True},
    )
    tag_keys = list(mesh.cell_tags.keys())
    for key in tag_keys:
        working.cell_tags[key] = []
    remeshed = 0
    removed = 0
    generated = 0
    for cid, (cell, ctype) in enumerate(zip(mesh.cells, mesh.cell_types or [])):
        ctype_l = str(ctype).lower()
        replacements: list[tuple[str, tuple[int, ...]]] = []
        if cid in set(bad):
            if ctype_l == "tet4" and len(cell) >= 4 and _cell_measure(mesh, cell, ctype_l) > float(min_volume):
                for tet in _subdivide_tet4_with_centroid(working, cell):
                    replacements.append(("tet4", tet))
                remeshed += 1
            elif ctype_l == "hex8" and len(cell) >= 8 and _cell_measure(mesh, cell, ctype_l) > float(min_volume):
                for tet in _split_hex8_to_tets(cell):
                    replacements.append(("tet4", tet))
                remeshed += 1
            else:
                removed += 1
        else:
            replacements.append((ctype_l, tuple(int(v) for v in cell)))
        for new_type, new_cell in replacements:
            working.cell_types.append(new_type)
            working.cells.append(tuple(new_cell))
            generated += 1 if cid in set(bad) else 0
            for key in tag_keys:
                vals = list(mesh.cell_tags.get(key, []) or [])
                working.cell_tags[key].append(vals[cid] if cid < len(vals) else "")
    try:
        apply_3d_boundary_tags(working)
    except Exception:
        pass
    after_vol = [_cell_measure(working, cell, ctype) for cell, ctype in zip(working.cells, working.cell_types or [])]
    after_asp = [_cell_aspect(working, cell) for cell in working.cells]
    working.quality = MeshQualityReport(
        min_quality=1.0 if working.cell_count > 0 else 0.0,
        max_aspect_ratio=max(after_asp) if after_asp else None,
        bad_cell_ids=[],
        warnings=[f"Locally remeshed {remeshed} bad cell(s) and removed {removed} unrecoverable cell(s)."],
    )
    report = LocalRemeshReport(
        ok=bool(working.cell_count > 0),
        original_cell_count=int(mesh.cell_count),
        remeshed_bad_cell_count=remeshed,
        removed_bad_cell_count=removed,
        generated_replacement_cell_count=generated,
        final_cell_count=int(working.cell_count),
        bad_cell_ids=tuple(int(v) for v in bad),
        actions=("mesh.bad_cells_locally_remeshed",) if remeshed else ("mesh.bad_cells_removed_unrecoverable",),
        diagnostics=(),
        metadata={
            "contract_version": "local_remesh_report_v1",
            "min_volume_before": min(volumes) if volumes else None,
            "min_volume_after": min(after_vol) if after_vol else None,
            "max_aspect_ratio_before": max(aspects) if aspects else None,
            "max_aspect_ratio_after": max(after_asp) if after_asp else None,
        },
    )
    working.metadata["local_remesh"] = report.to_dict()
    if attach and not isinstance(project_or_mesh, MeshDocument):
        project = as_project_context(project_or_mesh).get_project()
        if hasattr(getattr(project, "mesh_model", None), "attach_mesh"):
            project.mesh_model.attach_mesh(working)
    log_geometry_operation("local_volume_remesh", enabled=debug, debug_dir=debug_dir, input_state=_state_summary(mesh), output_state=report.to_dict(), status="ok" if report.ok else "error", diagnostics=report.diagnostics, start_counter=start_counter, started_at=started_at)
    return working, report


try:
    __all__ += [
        "build_gmsh_occ_fragment_tet4_mesh",
        "geometry_operation_log_status",
        "local_remesh_volume_mesh_quality",
    ]
except NameError:  # pragma: no cover
    __all__ = [
        "build_gmsh_occ_fragment_tet4_mesh",
        "geometry_operation_log_status",
        "local_remesh_volume_mesh_quality",
    ]
