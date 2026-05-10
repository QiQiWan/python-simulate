from __future__ import annotations

"""Dependency-light helpers for multi-STL geological region assembly.

The routines in this module deliberately avoid OCC/Gmsh imports.  They provide
stable contracts and deterministic fallbacks that allow the modular workflow to
reason about multiple STL shells, material mapping, and interface candidates in
headless environments.  High-order conformal tetrahedral meshing remains routed
through optional Gmsh-powered plugins when those dependencies are installed.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import math

from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport


@dataclass(frozen=True, slots=True)
class STLRegionSpec:
    """One imported STL region/shell and its material assignment."""

    region_id: str
    material_id: str = "imported_geology"
    role: str = "soil"
    cell_ids: tuple[int, ...] = ()
    node_ids: tuple[int, ...] = ()
    closed: bool = False
    manifold: bool = False
    bounds: tuple[float, float, float, float, float, float] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "material_id": self.material_id,
            "role": self.role,
            "cell_ids": [int(v) for v in self.cell_ids],
            "node_ids": [int(v) for v in self.node_ids],
            "closed": bool(self.closed),
            "manifold": bool(self.manifold),
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MultiSTLClosureReport:
    """Structured diagnosis for multi-STL region closure/readiness."""

    ready: bool
    region_count: int = 0
    closed_region_count: int = 0
    open_region_count: int = 0
    conformal_candidate_count: int = 0
    interface_candidate_count: int = 0
    issues: tuple[dict[str, Any], ...] = ()
    regions: tuple[STLRegionSpec, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": bool(self.ready),
            "region_count": int(self.region_count),
            "closed_region_count": int(self.closed_region_count),
            "open_region_count": int(self.open_region_count),
            "conformal_candidate_count": int(self.conformal_candidate_count),
            "interface_candidate_count": int(self.interface_candidate_count),
            "issues": [dict(row) for row in self.issues],
            "regions": [row.to_dict() for row in self.regions],
            "metadata": dict(self.metadata),
        }


def _values_for(mesh: MeshDocument, tag: str, default: str) -> list[str]:
    raw = list(mesh.cell_tags.get(tag, []) or [])
    if not raw:
        return [default] * int(mesh.cell_count)
    if len(raw) < int(mesh.cell_count):
        raw = raw + [raw[-1] if raw else default] * (int(mesh.cell_count) - len(raw))
    return [str(v) for v in raw[: int(mesh.cell_count)]]


def _bounds_for_nodes(mesh: MeshDocument, node_ids: Iterable[int]) -> tuple[float, float, float, float, float, float]:
    pts = [mesh.nodes[int(i)] for i in node_ids if 0 <= int(i) < int(mesh.node_count)]
    if not pts:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    zs = [float(p[2]) for p in pts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _edge_use_count(mesh: MeshDocument, cell_ids: Iterable[int]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for cid in cell_ids:
        cell = tuple(int(v) for v in mesh.cells[int(cid)])
        if len(cell) < 3:
            continue
        for a, b in ((cell[0], cell[1]), (cell[1], cell[2]), (cell[2], cell[0])):
            key = (min(a, b), max(a, b))
            counts[key] = counts.get(key, 0) + 1
    return counts


def surface_region_specs(mesh: MeshDocument) -> tuple[STLRegionSpec, ...]:
    """Group a surface MeshDocument by block/region tags."""

    if mesh is None:
        return ()
    block_ids = _values_for(mesh, "block_id", "imported_region")
    material_ids = _values_for(mesh, "material_id", "imported_geology")
    roles = _values_for(mesh, "role", "geology_surface")
    groups: dict[str, list[int]] = {}
    for cid, block_id in enumerate(block_ids):
        groups.setdefault(str(block_id), []).append(int(cid))
    specs: list[STLRegionSpec] = []
    for region_id, cell_ids in sorted(groups.items()):
        node_ids = sorted({int(node) for cid in cell_ids for node in tuple(mesh.cells[cid])})
        edge_counts = _edge_use_count(mesh, cell_ids)
        boundary_edges = sum(1 for count in edge_counts.values() if count == 1)
        nonmanifold_edges = sum(1 for count in edge_counts.values() if count > 2)
        closed = bool(cell_ids) and boundary_edges == 0 and nonmanifold_edges == 0
        first_cell = cell_ids[0] if cell_ids else 0
        material_id = material_ids[first_cell] if first_cell < len(material_ids) else "imported_geology"
        role = roles[first_cell] if first_cell < len(roles) else "geology_surface"
        specs.append(
            STLRegionSpec(
                region_id=str(region_id),
                material_id=str(material_id),
                role=str(role),
                cell_ids=tuple(cell_ids),
                node_ids=tuple(node_ids),
                closed=closed,
                manifold=closed,
                bounds=_bounds_for_nodes(mesh, node_ids),
                metadata={
                    "surface_cell_count": int(len(cell_ids)),
                    "surface_node_count": int(len(node_ids)),
                    "boundary_edge_count": int(boundary_edges),
                    "nonmanifold_edge_count": int(nonmanifold_edges),
                },
            )
        )
    return tuple(specs)


def diagnose_multi_stl_closure(mesh: MeshDocument) -> MultiSTLClosureReport:
    specs = surface_region_specs(mesh)
    issues: list[dict[str, Any]] = []
    conformal_candidates = 0
    for spec in specs:
        node_count = len(spec.node_ids)
        if spec.closed:
            if node_count in {4, 8}:
                conformal_candidates += 1
        else:
            issues.append(
                {
                    "severity": "error",
                    "code": "stl_region.open_surface",
                    "message": "STL region is not a closed manifold shell; conformal volume meshing requires closure or geological volume construction.",
                    "region_id": spec.region_id,
                    "metadata": dict(spec.metadata),
                }
            )
    interface_candidates = _interface_candidate_pairs(specs)
    ready = bool(specs) and all(spec.closed for spec in specs)
    return MultiSTLClosureReport(
        ready=ready,
        region_count=len(specs),
        closed_region_count=sum(1 for row in specs if row.closed),
        open_region_count=sum(1 for row in specs if not row.closed),
        conformal_candidate_count=conformal_candidates,
        interface_candidate_count=len(interface_candidates),
        issues=tuple(issues),
        regions=specs,
        metadata={"interface_candidates": interface_candidates},
    )


def combine_mesh_documents(meshes: Iterable[MeshDocument], *, metadata: Mapping[str, Any] | None = None) -> MeshDocument:
    """Combine several disjoint STL surface MeshDocuments into one surface mesh."""

    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    cell_tags: dict[str, list[Any]] = {}
    face_tags: dict[str, list[Any]] = {}
    node_offset = 0
    warnings: list[str] = []
    sources: list[dict[str, Any]] = []
    for index, mesh in enumerate(meshes):
        if mesh is None:
            continue
        current_offset = node_offset
        nodes.extend([tuple(float(v) for v in row) for row in mesh.nodes])
        cells.extend([tuple(int(v) + current_offset for v in cell) for cell in mesh.cells])
        cell_types.extend([str(v) for v in (mesh.cell_types or ["tri3"] * mesh.cell_count)])
        for key, values in mesh.cell_tags.items():
            cell_tags.setdefault(key, []).extend(list(values))
        for key, values in mesh.face_tags.items():
            face_tags.setdefault(key, []).extend(list(values))
        if mesh.quality and mesh.quality.warnings:
            warnings.extend([f"mesh[{index}]: {msg}" for msg in mesh.quality.warnings])
        sources.append({"index": index, "node_count": mesh.node_count, "cell_count": mesh.cell_count, "metadata": dict(mesh.metadata)})
        node_offset += int(mesh.node_count)
    for key, values in list(cell_tags.items()):
        if len(values) < len(cells):
            values.extend([values[-1] if values else ""] * (len(cells) - len(values)))
            cell_tags[key] = values
    out = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags=cell_tags,
        face_tags=face_tags,
        quality=MeshQualityReport(min_quality=0.0 if warnings else 1.0, warnings=warnings),
        metadata={
            "source": "multi_stl_surface_combiner",
            "mesh_kind": "multi_stl_tri_surface",
            "mesh_role": "geometry_surface",
            "mesh_dimension": 2,
            "cell_families": sorted({str(v).lower() for v in cell_types}),
            "surface_mesh_only": True,
            "requires_volume_meshing": True,
            "solid_solver_ready": False,
            "source_meshes": sources,
            **dict(metadata or {}),
        },
    )
    report = diagnose_multi_stl_closure(out)
    out.metadata["multi_stl_closure"] = report.to_dict()
    return out


def _bbox_touch(a: tuple[float, float, float, float, float, float], b: tuple[float, float, float, float, float, float], *, tol: float = 1.0e-8) -> bool:
    ax0, ax1, ay0, ay1, az0, az1 = a
    bx0, bx1, by0, by1, bz0, bz1 = b
    overlap_x = min(ax1, bx1) - max(ax0, bx0)
    overlap_y = min(ay1, by1) - max(ay0, by0)
    overlap_z = min(az1, bz1) - max(az0, bz0)
    overlaps = [overlap_x, overlap_y, overlap_z]
    near = [abs(v) <= tol for v in overlaps]
    positive = [v >= -tol for v in overlaps]
    return all(positive) and any(near)


def _interface_candidate_pairs(specs: Iterable[STLRegionSpec]) -> list[dict[str, Any]]:
    rows = list(specs)
    out: list[dict[str, Any]] = []
    for i, a in enumerate(rows):
        if a.bounds is None:
            continue
        for b in rows[i + 1 :]:
            if b.bounds is None:
                continue
            if _bbox_touch(a.bounds, b.bounds):
                out.append({"master_ref": a.region_id, "slave_ref": b.region_id, "mode": "bbox_touch_candidate"})
    return out


def _tet_quality(nodes: list[tuple[float, float, float]], tet: tuple[int, int, int, int]) -> float:
    pts = [nodes[i] for i in tet]
    ax, ay, az = pts[0]
    bx, by, bz = pts[1]
    cx, cy, cz = pts[2]
    dx, dy, dz = pts[3]
    v = abs(
        (bx - ax) * ((cy - ay) * (dz - az) - (cz - az) * (dy - ay))
        - (by - ay) * ((cx - ax) * (dz - az) - (cz - az) * (dx - ax))
        + (bz - az) * ((cx - ax) * (dy - ay) - (cy - ay) * (dx - ax))
    ) / 6.0
    edges = []
    for p in range(4):
        for q in range(p + 1, 4):
            edges.append(math.dist(pts[p], pts[q]))
    longest = max(edges) if edges else 1.0
    return float(max(0.0, min(1.0, 6.0 * v / max(longest**3, 1.0e-12))))


def deterministic_conformal_tet4_from_closed_regions(surface: MeshDocument) -> MeshDocument | None:
    """Create a deterministic Tet4 volume mesh for simple closed STL regions.

    This is not a replacement for Gmsh.  It supports small canonical closed STL
    shells used by tests and dependency-light workflows: tetrahedral shells and
    axis-aligned hexahedral/cube shells.  Complex shells should be routed to
    gmsh_tet4/conformal meshing.
    """

    specs = surface_region_specs(surface)
    if not specs or not all(spec.closed for spec in specs):
        return None
    nodes: list[tuple[float, float, float]] = []
    node_map: dict[int, int] = {}
    cells: list[tuple[int, int, int, int]] = []
    cell_materials: list[str] = []
    cell_blocks: list[str] = []
    warnings: list[str] = []

    def mapped_node(old_id: int) -> int:
        if old_id not in node_map:
            node_map[old_id] = len(nodes)
            nodes.append(tuple(float(v) for v in surface.nodes[int(old_id)]))
        return node_map[old_id]

    for spec in specs:
        ids = list(spec.node_ids)
        if len(ids) == 4:
            tet = tuple(mapped_node(i) for i in ids)
            cells.append(tet)  # type: ignore[arg-type]
            cell_materials.append(spec.material_id)
            cell_blocks.append(spec.region_id)
        elif len(ids) == 8:
            # Map an axis-aligned shell into a hexahedral node ordering, then use
            # the same 5-tet decomposition as the solid solver uses for Hex8.
            pts = {i: tuple(float(v) for v in surface.nodes[i]) for i in ids}
            sorted_ids = sorted(ids, key=lambda i: (pts[i][2], pts[i][1], pts[i][0]))
            lower = sorted(sorted_ids[:4], key=lambda i: (pts[i][1], pts[i][0]))
            upper = sorted(sorted_ids[4:], key=lambda i: (pts[i][1], pts[i][0]))
            # Hex8 order: zmin [xmin/ymin, xmax/ymin, xmax/ymax, xmin/ymax], zmax same.
            def ordered_quad(rows: list[int]) -> list[int]:
                by_y = sorted(rows, key=lambda i: (pts[i][1], pts[i][0]))
                bottom = sorted(by_y[:2], key=lambda i: pts[i][0])
                top = sorted(by_y[2:], key=lambda i: pts[i][0])
                return [bottom[0], bottom[1], top[1], top[0]]
            hex_nodes = [mapped_node(i) for i in ordered_quad(lower) + ordered_quad(upper)]
            for tet_idx in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
                cells.append(tuple(hex_nodes[i] for i in tet_idx))
                cell_materials.append(spec.material_id)
                cell_blocks.append(spec.region_id)
        else:
            warnings.append(f"Region {spec.region_id}: deterministic fallback supports only 4-node tetra or 8-node hexahedral shells; got {len(ids)} nodes.")
    if not cells:
        return None
    qualities = [_tet_quality(nodes, cell) for cell in cells]
    min_q = min(qualities) if qualities else None
    return MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["tet4"] * len(cells),
        cell_tags={
            "block_id": list(cell_blocks),
            "region_name": list(cell_blocks),
            "role": ["solid_volume"] * len(cells),
            "material_id": list(cell_materials),
        },
        face_tags={"interface_candidates": _interface_candidate_pairs(specs)},
        quality=MeshQualityReport(min_quality=min_q, warnings=warnings),
        metadata={
            "source": "deterministic_multi_stl_tet4_fallback",
            "mesh_kind": "conformal_tet4_from_stl_regions",
            "mesh_role": "solid_volume",
            "mesh_dimension": 3,
            "cell_families": ["tet4"],
            "solid_solver_ready": True,
            "requires_volume_meshing": False,
            "region_count": len(specs),
            "multi_stl_closure": diagnose_multi_stl_closure(surface).to_dict(),
            "conformal": True,
            "fallback": "deterministic_closed_region_tet4",
        },
    )


def audit_region_material_mapping(project_or_mesh: Any, *, material_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """Audit cell-region material tags against a project material library."""

    mesh = project_or_mesh if isinstance(project_or_mesh, MeshDocument) else getattr(getattr(project_or_mesh, "mesh_model", None), "mesh_document", None)
    known = set(str(v) for v in (material_ids or []))
    if not known and not isinstance(project_or_mesh, MeshDocument):
        lib = getattr(project_or_mesh, "material_library", None)
        if lib is not None and hasattr(lib, "material_ids"):
            known = set(str(v) for v in lib.material_ids())
    if mesh is None:
        return {"ok": False, "issue_count": 1, "issues": [{"code": "mesh.missing", "severity": "error"}], "region_count": 0}
    materials = [str(v) for v in list(mesh.cell_tags.get("material_id", []) or [])]
    blocks = [str(v) for v in list(mesh.cell_tags.get("block_id", []) or [])]
    regions = sorted(set(blocks or ["default_region"]))
    missing = sorted({mid for mid in materials if mid and known and mid not in known})
    unassigned_cells = [i for i in range(mesh.cell_count) if i >= len(materials) or not materials[i]]
    issues: list[dict[str, Any]] = []
    if missing:
        issues.append({"severity": "error", "code": "material.missing_records", "message": "Some mesh material IDs are not defined in the project material library.", "material_ids": missing})
    if unassigned_cells:
        issues.append({"severity": "error", "code": "material.unassigned_cells", "message": "Some cells have no material_id tag.", "cell_ids": unassigned_cells[:20], "count": len(unassigned_cells)})
    return {
        "ok": not any(row.get("severity") == "error" for row in issues),
        "issue_count": len(issues),
        "issues": issues,
        "region_count": len(regions),
        "regions": regions,
        "material_ids": sorted(set(materials)),
        "known_material_ids": sorted(known),
    }


__all__ = [
    "MultiSTLClosureReport",
    "STLRegionSpec",
    "audit_region_material_mapping",
    "combine_mesh_documents",
    "deterministic_conformal_tet4_from_closed_regions",
    "diagnose_multi_stl_closure",
    "surface_region_specs",
]
