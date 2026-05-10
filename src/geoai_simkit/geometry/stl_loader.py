from __future__ import annotations

"""STL geological model loader.

The loader is intentionally dependency-light.  It reads ASCII or binary STL,
merges duplicate vertices, performs engineering quality checks, and exposes the
result through the lightweight mesh/document contracts used by the GUI and
headless FEM pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
import json
import math
import re
import struct
from typing import Any, Iterable

import numpy as np

from geoai_simkit.core.model import GeometryObjectRecord, MaterialBinding, SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.pipeline.specs import SimpleUnstructuredGrid


@dataclass(slots=True)
class STLImportOptions:
    name: str | None = None
    unit_scale: float = 1.0
    merge_tolerance: float = 1.0e-9
    role: str = "geology_surface"
    material_id: str = "imported_geology"
    vertical_axis: str = "z"
    flip_normals: bool = False
    center_to_origin: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class STLQualityReport:
    triangle_count: int = 0
    vertex_count: int = 0
    degenerate_triangle_count: int = 0
    duplicate_triangle_count: int = 0
    boundary_edge_count: int = 0
    nonmanifold_edge_count: int = 0
    connected_component_count: int = 0
    is_closed: bool = False
    is_manifold: bool = False
    signed_volume: float = 0.0
    surface_area: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangle_count": int(self.triangle_count),
            "vertex_count": int(self.vertex_count),
            "degenerate_triangle_count": int(self.degenerate_triangle_count),
            "duplicate_triangle_count": int(self.duplicate_triangle_count),
            "boundary_edge_count": int(self.boundary_edge_count),
            "nonmanifold_edge_count": int(self.nonmanifold_edge_count),
            "connected_component_count": int(self.connected_component_count),
            "is_closed": bool(self.is_closed),
            "is_manifold": bool(self.is_manifold),
            "signed_volume": float(self.signed_volume),
            "surface_area": float(self.surface_area),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class STLGeologyMesh:
    name: str
    vertices: np.ndarray
    triangles: np.ndarray
    normals: np.ndarray
    source_path: str
    unit_scale: float = 1.0
    role: str = "geology_surface"
    material_id: str = "imported_geology"
    quality: STLQualityReport = field(default_factory=STLQualityReport)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def bounds(self) -> tuple[float, float, float, float, float, float]:
        if self.vertices.size == 0:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        mins = self.vertices.min(axis=0)
        maxs = self.vertices.max(axis=0)
        return (float(mins[0]), float(maxs[0]), float(mins[1]), float(maxs[1]), float(mins[2]), float(maxs[2]))

    @property
    def centroid(self) -> tuple[float, float, float]:
        if self.vertices.size == 0:
            return (0.0, 0.0, 0.0)
        center = self.vertices.mean(axis=0)
        return (float(center[0]), float(center[1]), float(center[2]))

    def to_mesh_document(self, *, block_id: str | None = None) -> MeshDocument:
        bid = block_id or self.name
        return MeshDocument(
            nodes=[tuple(float(v) for v in row) for row in self.vertices.tolist()],
            cells=[tuple(int(i) for i in tri) for tri in self.triangles.tolist()],
            cell_types=["tri3"] * int(len(self.triangles)),
            cell_tags={
                "block_id": [bid] * int(len(self.triangles)),
                "region_name": [bid] * int(len(self.triangles)),
                "role": [self.role] * int(len(self.triangles)),
                "material_id": [self.material_id] * int(len(self.triangles)),
            },
            quality=MeshQualityReport(
                min_quality=0.0 if self.quality.degenerate_triangle_count else 1.0,
                max_aspect_ratio=None,
                bad_cell_ids=[],
                warnings=list(self.quality.warnings),
            ),
            metadata={
                "source": "stl_geology_loader",
                "source_path": self.source_path,
                "bounds": list(self.bounds),
                "quality": self.quality.to_dict(),
                "mesh_kind": "stl_tri_surface",
                "mesh_role": "geometry_surface",
                "mesh_dimension": 2,
                "cell_families": ["tri3"],
                "surface_mesh_only": True,
                "requires_volume_meshing": True,
                "solid_solver_ready": False,
                "closed_surface": bool(self.quality.is_closed),
                **dict(self.metadata),
            },
        )

    def to_simple_grid(self, *, region_name: str | None = None) -> SimpleUnstructuredGrid:
        region = region_name or self.name
        grid = SimpleUnstructuredGrid(
            points=self.vertices.tolist(),
            cells=[tuple(int(i) for i in tri) for tri in self.triangles.tolist()],
            celltypes=["tri3"] * int(len(self.triangles)),
            region_names=[region] * int(len(self.triangles)),
        )
        grid.cell_data["role"] = np.asarray([self.role] * int(len(self.triangles)), dtype=object)
        grid.cell_data["material_name"] = np.asarray([self.material_id] * int(len(self.triangles)), dtype=object)
        grid.cell_data["block_tag"] = np.asarray([region] * int(len(self.triangles)), dtype=object)
        payload = self.to_summary_dict()
        grid.field_data["source_kind"] = ["stl_geology"]
        grid.field_data["stl_geology_json"] = json.dumps(payload, ensure_ascii=False)
        return grid

    def to_simulation_model(self, *, model_name: str | None = None) -> SimulationModel:
        region_name = self.name
        cells = np.arange(int(len(self.triangles)), dtype=np.int64)
        model = SimulationModel(
            name=model_name or self.name,
            mesh=self.to_simple_grid(region_name=region_name),
            region_tags=[
                RegionTag(
                    name=region_name,
                    cell_ids=cells,
                    metadata={
                        "source": "stl_geology_loader",
                        "role": self.role,
                        "material_name": self.material_id,
                        "bounds": list(self.bounds),
                        "quality": self.quality.to_dict(),
                    },
                )
            ],
            materials=[
                MaterialBinding(
                    region_name=region_name,
                    material_name=self.material_id,
                    parameters={"source": "stl_import", "unit_scale": float(self.unit_scale)},
                    metadata={"auto_generated": True, "loader": "stl_geology_loader"},
                )
            ],
            object_records=[
                GeometryObjectRecord(
                    key=f"object:{region_name}",
                    name=region_name,
                    object_type="stl_surface_mesh",
                    region_name=region_name,
                    metadata={
                        "source": "stl_geology_loader",
                        "source_path": self.source_path,
                        "role": self.role,
                        "bounds": list(self.bounds),
                        "quality": self.quality.to_dict(),
                    },
                )
            ],
            metadata={
                "geometry_state": "surface_mesh",
                "stl_geology": self.to_summary_dict(),
                "pipeline.builder": "stl_geology_loader",
            },
        )
        return model

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "unit_scale": float(self.unit_scale),
            "role": self.role,
            "material_id": self.material_id,
            "bounds": list(self.bounds),
            "centroid": list(self.centroid),
            "vertex_count": int(len(self.vertices)),
            "triangle_count": int(len(self.triangles)),
            "quality": self.quality.to_dict(),
            "metadata": dict(self.metadata),
        }


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(value).strip())
    cleaned = cleaned.strip("_") or "imported_stl"
    if cleaned[0].isdigit():
        cleaned = f"stl_{cleaned}"
    return cleaned[:96]


def _is_binary_stl(path: Path, data: bytes) -> bool:
    if len(data) < 84:
        return False
    try:
        tri_count = struct.unpack("<I", data[80:84])[0]
    except Exception:
        return False
    expected = 84 + int(tri_count) * 50
    if expected == len(data):
        return True
    head = data[:256].lstrip().lower()
    return not head.startswith(b"solid")


def _parse_binary_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    tri_count = struct.unpack("<I", data[80:84])[0]
    offset = 84
    normals: list[tuple[float, float, float]] = []
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []
    for _ in range(int(tri_count)):
        if offset + 50 > len(data):
            break
        row = struct.unpack("<12fH", data[offset: offset + 50])
        normals.append((float(row[0]), float(row[1]), float(row[2])))
        triangles.append(((float(row[3]), float(row[4]), float(row[5])), (float(row[6]), float(row[7]), float(row[8])), (float(row[9]), float(row[10]), float(row[11]))))
        offset += 50
    return np.asarray(normals, dtype=float), np.asarray(triangles, dtype=float)


def _parse_ascii_stl(text: str) -> tuple[np.ndarray, np.ndarray]:
    normals: list[tuple[float, float, float]] = []
    triangles: list[list[tuple[float, float, float]]] = []
    current_normal = (0.0, 0.0, 0.0)
    current_vertices: list[tuple[float, float, float]] = []
    float_re = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    normal_re = re.compile(rf"facet\s+normal\s+({float_re})\s+({float_re})\s+({float_re})", re.I)
    vertex_re = re.compile(rf"vertex\s+({float_re})\s+({float_re})\s+({float_re})", re.I)
    for line in text.splitlines():
        nmatch = normal_re.search(line)
        if nmatch:
            current_normal = tuple(float(nmatch.group(i)) for i in range(1, 4))  # type: ignore[assignment]
            current_vertices = []
            continue
        vmatch = vertex_re.search(line)
        if vmatch:
            current_vertices.append(tuple(float(vmatch.group(i)) for i in range(1, 4)))
            if len(current_vertices) == 3:
                triangles.append(list(current_vertices))
                normals.append(current_normal)
                current_vertices = []
    return np.asarray(normals, dtype=float), np.asarray(triangles, dtype=float)


def _merge_vertices(raw_triangles: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    if raw_triangles.size == 0:
        return np.zeros((0, 3), dtype=float), np.zeros((0, 3), dtype=np.int64)
    tol = abs(float(tolerance)) or 0.0
    vertex_map: dict[tuple[int, int, int] | tuple[float, float, float], int] = {}
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for tri in raw_triangles.reshape((-1, 3, 3)):
        face: list[int] = []
        for p in tri:
            if tol > 0.0:
                key = tuple(int(round(float(v) / tol)) for v in p)
            else:
                key = tuple(float(v) for v in p)
            idx = vertex_map.get(key)
            if idx is None:
                idx = len(vertices)
                vertex_map[key] = idx
                vertices.append((float(p[0]), float(p[1]), float(p[2])))
            face.append(idx)
        faces.append((face[0], face[1], face[2]))
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def _triangle_areas_and_normals(vertices: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(triangles) == 0:
        return np.zeros((0,), dtype=float), np.zeros((0, 3), dtype=float)
    p0 = vertices[triangles[:, 0]]
    p1 = vertices[triangles[:, 1]]
    p2 = vertices[triangles[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    norm = np.linalg.norm(cross, axis=1)
    areas = 0.5 * norm
    normals = np.zeros_like(cross)
    ok = norm > 0.0
    normals[ok] = cross[ok] / norm[ok].reshape((-1, 1))
    return areas, normals


def _connected_components(triangles: np.ndarray) -> int:
    if len(triangles) == 0:
        return 0
    vertex_to_faces: dict[int, list[int]] = {}
    for fid, tri in enumerate(triangles.tolist()):
        for vid in tri:
            vertex_to_faces.setdefault(int(vid), []).append(fid)
    visited = np.zeros((len(triangles),), dtype=bool)
    count = 0
    for seed in range(len(triangles)):
        if visited[seed]:
            continue
        count += 1
        stack = [seed]
        visited[seed] = True
        while stack:
            fid = stack.pop()
            for vid in triangles[fid].tolist():
                for nb in vertex_to_faces.get(int(vid), []):
                    if not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
    return int(count)


def _quality(vertices: np.ndarray, triangles: np.ndarray, normals: np.ndarray) -> STLQualityReport:
    areas, computed_normals = _triangle_areas_and_normals(vertices, triangles)
    edge_counts: dict[tuple[int, int], int] = {}
    duplicate_keys: set[tuple[int, int, int]] = set()
    duplicate_count = 0
    for tri in triangles.tolist():
        key = tuple(sorted(int(v) for v in tri))
        if key in duplicate_keys:
            duplicate_count += 1
        else:
            duplicate_keys.add(key)
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            e = tuple(sorted((int(a), int(b))))
            edge_counts[e] = edge_counts.get(e, 0) + 1
    boundary = sum(1 for c in edge_counts.values() if c == 1)
    nonmanifold = sum(1 for c in edge_counts.values() if c > 2)
    signed_volume = 0.0
    if len(triangles):
        p0 = vertices[triangles[:, 0]]
        p1 = vertices[triangles[:, 1]]
        p2 = vertices[triangles[:, 2]]
        signed_volume = float(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum() / 6.0)
    warnings: list[str] = []
    degenerate = int(np.count_nonzero(areas <= max(float(np.finfo(float).eps), 1.0e-14)))
    if degenerate:
        warnings.append(f"{degenerate} degenerate triangles were found.")
    if boundary:
        warnings.append(f"{boundary} boundary edges indicate the STL is an open surface, not a closed volume.")
    if nonmanifold:
        warnings.append(f"{nonmanifold} non-manifold edges were found.")
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate triangles were found.")
    if len(normals) == len(computed_normals) and len(normals):
        given_norm = np.linalg.norm(normals, axis=1)
        ok = given_norm > 1.0e-14
        if np.any(ok):
            dot = np.einsum("ij,ij->i", normals[ok] / given_norm[ok].reshape((-1, 1)), computed_normals[ok])
            flipped = int(np.count_nonzero(dot < -0.5))
            if flipped > max(3, int(0.1 * len(dot))):
                warnings.append("Many stored STL normals are opposite to triangle winding; computed normals are used for preview/assembly metadata.")
    return STLQualityReport(
        triangle_count=int(len(triangles)),
        vertex_count=int(len(vertices)),
        degenerate_triangle_count=degenerate,
        duplicate_triangle_count=int(duplicate_count),
        boundary_edge_count=int(boundary),
        nonmanifold_edge_count=int(nonmanifold),
        connected_component_count=_connected_components(triangles),
        is_closed=boundary == 0 and len(triangles) > 0,
        is_manifold=nonmanifold == 0 and len(triangles) > 0,
        signed_volume=float(signed_volume),
        surface_area=float(areas.sum()),
        warnings=warnings,
    )


def load_stl_geology(path: str | Path, options: STLImportOptions | None = None) -> STLGeologyMesh:
    opts = options or STLImportOptions()
    source = Path(path)
    data = source.read_bytes()
    if _is_binary_stl(source, data):
        given_normals, raw_triangles = _parse_binary_stl(data)
        stl_format = "binary"
    else:
        given_normals, raw_triangles = _parse_ascii_stl(data.decode("utf-8", errors="ignore"))
        stl_format = "ascii"
    if raw_triangles.size == 0:
        raise ValueError(f"No triangles were read from STL file: {source}")
    scale = float(opts.unit_scale or 1.0)
    raw_triangles = raw_triangles.astype(float) * scale
    vertices, triangles = _merge_vertices(raw_triangles, float(opts.merge_tolerance))
    if bool(opts.flip_normals) and len(triangles):
        triangles = triangles[:, [0, 2, 1]]
    if bool(opts.center_to_origin) and len(vertices):
        center = vertices.mean(axis=0).reshape((1, 3))
        vertices = vertices - center
    _, computed_normals = _triangle_areas_and_normals(vertices, triangles)
    quality = _quality(vertices, triangles, given_normals)
    name = _safe_name(opts.name or source.stem)
    return STLGeologyMesh(
        name=name,
        vertices=vertices,
        triangles=triangles,
        normals=computed_normals,
        source_path=str(source),
        unit_scale=scale,
        role=str(opts.role or "geology_surface"),
        material_id=str(opts.material_id or "imported_geology"),
        quality=quality,
        metadata={"stl_format": stl_format, **dict(opts.metadata)},
    )


def merge_simple_grids(base: Any, overlay: SimpleUnstructuredGrid) -> SimpleUnstructuredGrid:
    """Append an imported STL surface grid to an existing lightweight grid.

    The function is conservative: if the existing mesh does not look like the
    internal SimpleUnstructuredGrid contract, callers should replace the model
    instead of merging.
    """
    if not hasattr(base, "points") or not hasattr(base, "cells"):
        raise TypeError("Only SimpleUnstructuredGrid-like meshes can be merged without PyVista.")
    base_points = np.asarray(getattr(base, "points", []), dtype=float).reshape((-1, 3))
    overlay_points = np.asarray(getattr(overlay, "points", []), dtype=float).reshape((-1, 3))
    offset = int(len(base_points))
    points = np.vstack([base_points, overlay_points]) if len(base_points) else overlay_points
    base_cells = [tuple(int(i) for i in cell) for cell in list(getattr(base, "cells", []) or [])]
    overlay_cells = [tuple(int(i) + offset for i in cell) for cell in list(getattr(overlay, "cells", []) or [])]
    celltypes = list(getattr(base, "celltypes", []) or ["unknown"] * len(base_cells)) + list(getattr(overlay, "celltypes", []) or ["tri3"] * len(overlay_cells))
    merged = SimpleUnstructuredGrid(points=points.tolist(), cells=base_cells + overlay_cells, celltypes=celltypes)
    keys = set((getattr(base, "cell_data", {}) or {}).keys()) | set((getattr(overlay, "cell_data", {}) or {}).keys())
    for key in keys:
        left = list((getattr(base, "cell_data", {}) or {}).get(key, [""] * len(base_cells)))
        right = list((getattr(overlay, "cell_data", {}) or {}).get(key, [""] * len(overlay_cells)))
        if len(left) < len(base_cells):
            left.extend([""] * (len(base_cells) - len(left)))
        if len(right) < len(overlay_cells):
            right.extend([""] * (len(overlay_cells) - len(right)))
        merged.cell_data[key] = np.asarray(left + right, dtype=object)
    merged.field_data.update(dict(getattr(base, "field_data", {}) or {}))
    merged.field_data["merged_stl_geology"] = ["true"]
    return merged


__all__ = [
    "STLImportOptions",
    "STLQualityReport",
    "STLGeologyMesh",
    "load_stl_geology",
    "merge_simple_grids",
]
