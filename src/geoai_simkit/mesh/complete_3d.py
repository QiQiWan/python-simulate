from __future__ import annotations

"""Complete 3D mesh topology utilities.

This module is dependency-light and works directly on MeshDocument-like objects.
It extracts exterior boundary faces, internal region interfaces, volume regions
and boundary sets for Tet4/Hex8 solid meshes.
"""

from collections import defaultdict
from math import sqrt
from typing import Any, Iterable

from geoai_simkit.contracts.mesh import SOLID_CELL_TYPES, SURFACE_CELL_TYPES
from geoai_simkit.contracts.mesh3d import Mesh3DBoundaryFace, Mesh3DBoundarySet, Mesh3DInterfacePair, Mesh3DRegion, Mesh3DTopologyReport

_TET4_FACES: tuple[tuple[int, ...], ...] = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
_HEX8_FACES: tuple[tuple[int, ...], ...] = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
_WEDGE6_FACES: tuple[tuple[int, ...], ...] = ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5))
_PYRAMID5_FACES: tuple[tuple[int, ...], ...] = ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4))


def _points(mesh: Any) -> list[tuple[float, float, float]]:
    return [tuple(float(v) for v in row[:3]) for row in list(getattr(mesh, "nodes", []) or [])]


def _cells(mesh: Any) -> list[tuple[int, ...]]:
    return [tuple(int(v) for v in row) for row in list(getattr(mesh, "cells", []) or [])]


def _cell_types(mesh: Any) -> list[str]:
    return [str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])]


def _cell_tag(mesh: Any, name: str, index: int, fallback: str = "") -> str:
    tags = list(getattr(mesh, "cell_tags", {}).get(name) or [])
    return str(tags[index]) if index < len(tags) else fallback


def _cell_faces(cell: tuple[int, ...], cell_type: str) -> tuple[tuple[int, ...], ...]:
    ctype = str(cell_type).lower()
    if ctype.startswith("tet") and len(cell) >= 4:
        return tuple(tuple(cell[i] for i in face) for face in _TET4_FACES)
    if ctype.startswith("hex") and len(cell) >= 8:
        return tuple(tuple(cell[i] for i in face) for face in _HEX8_FACES)
    if ctype == "wedge6" and len(cell) >= 6:
        return tuple(tuple(cell[i] for i in face) for face in _WEDGE6_FACES)
    if ctype == "pyramid5" and len(cell) >= 5:
        return tuple(tuple(cell[i] for i in face) for face in _PYRAMID5_FACES)
    return ()


def _centroid(points: list[tuple[float, float, float]], nodes: Iterable[int]) -> tuple[float, float, float]:
    rows = [points[int(i)] for i in nodes]
    if not rows:
        return (0.0, 0.0, 0.0)
    n = float(len(rows))
    return (sum(p[0] for p in rows) / n, sum(p[1] for p in rows) / n, sum(p[2] for p in rows) / n)


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normal(points: list[tuple[float, float, float]], nodes: tuple[int, ...]) -> tuple[float, float, float]:
    if len(nodes) < 3:
        return (0.0, 0.0, 0.0)
    p0, p1, p2 = (points[int(nodes[0])], points[int(nodes[1])], points[int(nodes[2])])
    n = _cross(_sub(p1, p0), _sub(p2, p0))
    length = sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if length <= 0.0:
        return (0.0, 0.0, 0.0)
    return (n[0] / length, n[1] / length, n[2] / length)


def _bounds(points: list[tuple[float, float, float]]) -> tuple[float, float, float, float, float, float]:
    if not points:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _boundary_name(centroid: tuple[float, float, float], bounds: tuple[float, float, float, float, float, float], tol: float) -> str:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    x, y, z = centroid
    candidates: list[tuple[float, str]] = [
        (abs(x - xmin), "xmin"),
        (abs(x - xmax), "xmax"),
        (abs(y - ymin), "ymin"),
        (abs(y - ymax), "ymax"),
        (abs(z - zmin), "zmin"),
        (abs(z - zmax), "zmax"),
    ]
    distance, name = min(candidates, key=lambda row: row[0])
    span = max(xmax - xmin, ymax - ymin, zmax - zmin, 1.0)
    return name if distance <= max(tol, span * 1.0e-8) else "external"


def _tet_volume(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float:
    if len(cell) < 4:
        return 0.0
    a, b, c, d = [points[int(i)] for i in cell[:4]]
    ab = _sub(b, a)
    ac = _sub(c, a)
    ad = _sub(d, a)
    cr = _cross(ac, ad)
    return abs(ab[0] * cr[0] + ab[1] * cr[1] + ab[2] * cr[2]) / 6.0


def _hex_volume(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float:
    # Deterministic dependency-light approximation using the cell bounding box.
    # For structured Hex8 cells this is exact; for warped cells it is a conservative
    # diagnostic volume used by quality gates, not a solver integration rule.
    rows = [points[int(i)] for i in cell[:8]]
    xs = [p[0] for p in rows]
    ys = [p[1] for p in rows]
    zs = [p[2] for p in rows]
    return max(max(xs) - min(xs), 0.0) * max(max(ys) - min(ys), 0.0) * max(max(zs) - min(zs), 0.0)


def _cell_volume(points: list[tuple[float, float, float]], cell: tuple[int, ...], cell_type: str) -> float:
    ctype = str(cell_type).lower()
    if ctype.startswith("tet"):
        return _tet_volume(points, cell)
    if ctype.startswith("hex"):
        return _hex_volume(points, cell)
    return 0.0


def _boundary_face_records(mesh: Any, *, tolerance: float = 1.0e-9) -> tuple[list[Mesh3DBoundaryFace], int, int, list[Mesh3DInterfacePair]]:
    points = _points(mesh)
    cells = _cells(mesh)
    types = _cell_types(mesh)
    bounds = _bounds(points)
    owners: dict[tuple[int, ...], list[dict[str, object]]] = defaultdict(list)
    for cid, cell in enumerate(cells):
        ctype = types[cid] if cid < len(types) else "unknown"
        if ctype not in SOLID_CELL_TYPES:
            continue
        for face in _cell_faces(cell, ctype):
            owners[tuple(sorted(int(n) for n in face))].append({"cell_id": cid, "cell_type": ctype, "nodes": tuple(int(n) for n in face)})

    boundary_faces: list[Mesh3DBoundaryFace] = []
    internal_face_count = 0
    nonmanifold_face_count = 0
    interface_counter: dict[tuple[str, str], int] = defaultdict(int)
    for key, rows in owners.items():
        if len(rows) == 1:
            row = rows[0]
            cid = int(row["cell_id"])
            nodes = tuple(int(n) for n in row["nodes"])  # type: ignore[arg-type]
            centroid = _centroid(points, nodes)
            boundary_set = _boundary_name(centroid, bounds, tolerance)
            boundary_faces.append(
                Mesh3DBoundaryFace(
                    face_id=len(boundary_faces),
                    cell_id=cid,
                    cell_type=str(row["cell_type"]),
                    nodes=nodes,
                    boundary_set=boundary_set,
                    region_id=_cell_tag(mesh, "region_name", cid, _cell_tag(mesh, "block_id", cid, "region")),
                    material_id=_cell_tag(mesh, "material_id", cid, ""),
                    centroid=centroid,
                    normal=_normal(points, nodes),
                    metadata={"face_key": list(key)},
                )
            )
        elif len(rows) == 2:
            internal_face_count += 1
            a = int(rows[0]["cell_id"])
            b = int(rows[1]["cell_id"])
            ra = _cell_tag(mesh, "region_name", a, _cell_tag(mesh, "block_id", a, "region"))
            rb = _cell_tag(mesh, "region_name", b, _cell_tag(mesh, "block_id", b, "region"))
            if ra != rb:
                pair = tuple(sorted((ra, rb)))
                interface_counter[pair] += 1
        else:
            nonmanifold_face_count += 1

    materialized_candidates = list(getattr(mesh, "face_tags", {}).get("interface_candidates") or [])
    materialized_count = len(materialized_candidates)
    interface_pairs = [
        Mesh3DInterfacePair(pair_id=f"{a}::{b}", region_a=a, region_b=b, face_count=count, conformal=True, materialized=materialized_count > 0)
        for (a, b), count in sorted(interface_counter.items())
    ]
    return boundary_faces, internal_face_count, nonmanifold_face_count, interface_pairs


def extract_3d_boundary_faces(mesh: Any, *, tolerance: float = 1.0e-9) -> tuple[Mesh3DBoundaryFace, ...]:
    faces, _, _, _ = _boundary_face_records(mesh, tolerance=tolerance)
    return tuple(faces)


def build_mesh3d_topology_report(mesh: Any, *, tolerance: float = 1.0e-9) -> Mesh3DTopologyReport:
    points = _points(mesh)
    cells = _cells(mesh)
    types = _cell_types(mesh)
    solid_ids = [idx for idx, ctype in enumerate(types) if ctype in SOLID_CELL_TYPES]
    surface_ids = [idx for idx, ctype in enumerate(types) if ctype in SURFACE_CELL_TYPES]
    boundary_faces, internal_face_count, nonmanifold_face_count, interface_pairs = _boundary_face_records(mesh, tolerance=tolerance)

    set_faces: dict[str, list[Mesh3DBoundaryFace]] = defaultdict(list)
    for face in boundary_faces:
        set_faces[face.boundary_set].append(face)
    boundary_sets = tuple(
        Mesh3DBoundarySet(
            name=name,
            face_count=len(rows),
            cell_count=len({item.cell_id for item in rows}),
            node_count=len({node for item in rows for node in item.nodes}),
        )
        for name, rows in sorted(set_faces.items())
    )

    region_rows: dict[str, dict[str, object]] = defaultdict(lambda: {"cells": [], "nodes": set(), "types": set(), "volume": 0.0, "material_id": ""})
    for cid in solid_ids:
        cell = cells[cid]
        ctype = types[cid]
        region = _cell_tag(mesh, "region_name", cid, _cell_tag(mesh, "block_id", cid, "region"))
        material = _cell_tag(mesh, "material_id", cid, "")
        row = region_rows[region]
        row["cells"].append(cid)  # type: ignore[union-attr]
        row["nodes"].update(int(n) for n in cell)  # type: ignore[union-attr]
        row["types"].add(ctype)  # type: ignore[union-attr]
        row["volume"] = float(row["volume"]) + _cell_volume(points, cell, ctype)
        if material and not row["material_id"]:
            row["material_id"] = material
    regions = tuple(
        Mesh3DRegion(
            region_id=region,
            material_id=str(row["material_id"]),
            cell_count=len(row["cells"]),  # type: ignore[arg-type]
            node_count=len(row["nodes"]),  # type: ignore[arg-type]
            cell_types=tuple(sorted(str(v) for v in row["types"])),  # type: ignore[arg-type]
            volume=float(row["volume"]),
        )
        for region, row in sorted(region_rows.items())
    )
    diagnostics: list[str] = []
    if not solid_ids:
        diagnostics.append("mesh3d.no_solid_cells")
    if nonmanifold_face_count:
        diagnostics.append("mesh3d.nonmanifold_solid_faces")
    if not boundary_faces and solid_ids:
        diagnostics.append("mesh3d.no_boundary_faces")
    ok = bool(solid_ids and boundary_faces and nonmanifold_face_count == 0)
    return Mesh3DTopologyReport(
        ok=ok,
        node_count=len(points),
        cell_count=len(cells),
        solid_cell_count=len(solid_ids),
        surface_cell_count=len(surface_ids),
        boundary_face_count=len(boundary_faces),
        internal_face_count=internal_face_count,
        nonmanifold_face_count=nonmanifold_face_count,
        regions=regions,
        boundary_sets=boundary_sets,
        interface_pairs=tuple(interface_pairs),
        diagnostics=tuple(diagnostics),
        metadata={"contract_version": "mesh3d_topology_report_v1", "boundary_face_tagging": "xmin/xmax/ymin/ymax/zmin/zmax/external"},
    )


def apply_3d_boundary_tags(mesh: Any, *, tolerance: float = 1.0e-9) -> Mesh3DTopologyReport:
    """Mutate MeshDocument face_tags/metadata with extracted 3D boundary sets."""

    faces = extract_3d_boundary_faces(mesh, tolerance=tolerance)
    if not hasattr(mesh, "face_tags") or getattr(mesh, "face_tags", None) is None:
        mesh.face_tags = {}
    mesh.face_tags["boundary_face_ids"] = [item.face_id for item in faces]
    mesh.face_tags["boundary_face_cells"] = [item.cell_id for item in faces]
    mesh.face_tags["boundary_face_nodes"] = [list(item.nodes) for item in faces]
    mesh.face_tags["boundary_face_sets"] = [item.boundary_set for item in faces]
    mesh.face_tags["boundary_face_regions"] = [item.region_id for item in faces]
    mesh.face_tags["boundary_face_materials"] = [item.material_id for item in faces]
    mesh.face_tags["boundary_face_centroids"] = [list(item.centroid) for item in faces]
    mesh.face_tags["boundary_face_normals"] = [list(item.normal) for item in faces]
    boundary_sets = sorted({item.boundary_set for item in faces})
    mesh.face_tags["boundary_sets"] = boundary_sets
    if not hasattr(mesh, "metadata") or getattr(mesh, "metadata", None) is None:
        mesh.metadata = {}
    mesh.metadata["complete_3d_mesh"] = True
    mesh.metadata["boundary_face_count"] = len(faces)
    mesh.metadata["boundary_sets"] = list(boundary_sets)
    mesh.metadata["mesh3d_boundary_tagging"] = "complete_3d_boundary_tags_v1"
    return build_mesh3d_topology_report(mesh, tolerance=tolerance)


__all__ = [
    "apply_3d_boundary_tags",
    "build_mesh3d_topology_report",
    "extract_3d_boundary_faces",
]
