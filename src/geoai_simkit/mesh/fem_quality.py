from __future__ import annotations

"""Finite-element mesh display, quality and light repair helpers.

The routines in this module are deliberately dependency-light.  They operate on
``MeshDocument`` and ``GeoProjectDocument`` and avoid requiring Gmsh/OCC so they
can run in Qt-only startup mode.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport

FEM_MESH_QUALITY_CONTRACT = "geoai_simkit_fem_mesh_quality_v1"

_VOLUME_TYPES = {"tet4", "tetra", "tetra4", "hex8", "hexahedron", "wedge", "wedge6", "pyramid", "pyramid5"}
_SURFACE_TYPES = {"tri3", "triangle", "quad4", "quad"}


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: tuple[float, float, float]) -> float:
    return sqrt(max(0.0, _dot(a, a)))


def _tet_volume(points: list[tuple[float, float, float]]) -> float:
    if len(points) < 4:
        return 0.0
    a, b, c, d = points[:4]
    return abs(_dot(_sub(b, a), _cross(_sub(c, a), _sub(d, a)))) / 6.0


def _bbox_volume(points: list[tuple[float, float, float]]) -> float:
    if not points:
        return 0.0
    xs, ys, zs = zip(*points)
    return max(xs) - min(xs) * 0.0 if False else max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs)))


def _cell_points(mesh: MeshDocument, cell: tuple[int, ...]) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    n = len(mesh.nodes)
    for idx in cell:
        i = int(idx)
        if 0 <= i < n:
            p = mesh.nodes[i]
            pts.append((float(p[0]), float(p[1]), float(p[2])))
    return pts


def _edge_lengths(points: list[tuple[float, float, float]]) -> list[float]:
    lengths: list[float] = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            lengths.append(_norm(_sub(points[i], points[j])))
    return [v for v in lengths if v > 0.0]


def _aspect_ratio(points: list[tuple[float, float, float]]) -> float:
    lengths = _edge_lengths(points)
    if not lengths:
        return float("inf")
    return max(lengths) / max(min(lengths), 1.0e-12)


def _cell_measure(mesh: MeshDocument, cell: tuple[int, ...], ctype: str) -> float:
    points = _cell_points(mesh, cell)
    low = ctype.lower()
    if low.startswith("tet") or len(points) == 4:
        return _tet_volume(points)
    if low.startswith("hex") or "hexa" in low or len(points) == 8:
        # Robust coarse volume proxy.  It is sufficient for detecting zero-volume
        # imported cells and for FEM readiness gating.
        return _bbox_volume(points)
    if low.startswith("tri") and len(points) >= 3:
        return 0.5 * _norm(_cross(_sub(points[1], points[0]), _sub(points[2], points[0])))
    if low.startswith("quad") and len(points) >= 4:
        return 0.5 * _norm(_cross(_sub(points[1], points[0]), _sub(points[2], points[0]))) + 0.5 * _norm(_cross(_sub(points[2], points[0]), _sub(points[3], points[0])))
    return _bbox_volume(points)


def _cell_center(mesh: MeshDocument, cell: tuple[int, ...]) -> tuple[float, float, float]:
    pts = _cell_points(mesh, cell)
    if not pts:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / len(pts)
    return (sum(p[0] for p in pts) * inv, sum(p[1] for p in pts) * inv, sum(p[2] for p in pts) * inv)


def add_geology_layer_tags(mesh: MeshDocument, *, requested_layers: int = 8) -> dict[str, Any]:
    """Attach synthetic vertical layer tags when imported mesh has no layer data.

    Real geology files should ideally carry material/stratum cell data.  MSH/VTU
    files exported from external tools often do not, so this fallback uses cell
    center elevation bins.  The tags are explicit metadata and can later be
    overwritten by real strata/material assignments.
    """
    if mesh.cell_count <= 0:
        return {"layer_count": 0, "source": "empty_mesh"}
    preferred_keys = (
        "soil_id", "soilid", "soil", "soil_layer", "soil_layer_id",
        "stratum_id", "stratum", "strata", "strata_id",
        "layer_id", "layer", "geology_layer", "geology_layer_id",
        "lithology", "formation", "formation_id", "facies",
        "material_index", "material_id", "materialid", "material", "mat_id", "mat",
        "gmsh_physical", "gmsh:physical", "physical", "physical_group", "physical_id",
        "domain", "domain_id", "region", "region_id", "zone", "zone_id",
        "display_group",
    )
    lower_to_key = {str(k).lower().replace('-', '_').replace(':', '_').replace(' ', '_'): k for k in mesh.cell_tags}
    ordered_keys: list[str] = []
    for key in preferred_keys:
        real_key = lower_to_key.get(key.lower().replace('-', '_').replace(':', '_').replace(' ', '_'))
        if real_key is not None:
            ordered_keys.append(str(real_key))
    fuzzy_tokens = ("soil", "stratum", "strata", "layer", "geology", "lithology", "formation", "material", "physical", "gmsh", "domain", "region", "zone", "facies")
    for key in mesh.cell_tags:
        lower = str(key).lower()
        if lower.startswith("vtk"):
            continue
        if any(token in lower for token in fuzzy_tokens):
            ordered_keys.append(str(key))
    ordered_keys = list(dict.fromkeys(ordered_keys))
    existing = None
    existing_key = None
    valid = [(key, list(mesh.cell_tags.get(key, []))) for key in ordered_keys if len(list(mesh.cell_tags.get(key, []))) == mesh.cell_count]
    multi = [(key, values) for key, values in valid if len({str(v) for v in values}) > 1]
    for key, values in multi or valid:
        existing = values
        existing_key = key
        break
    if existing is not None and len(existing) == mesh.cell_count:
        unique = list(dict.fromkeys(str(v) for v in existing))
        mesh.cell_tags["geology_layer_id"] = [str(v) for v in existing]
        mesh.cell_tags.setdefault("display_group", [str(v) for v in existing])
        meta = {"layer_count": len(unique), "source": f"existing_cell_tags:{existing_key}", "scalar": existing_key, "layers": unique}
        mesh.metadata["geology_layer_display"] = meta
        mesh.metadata["preferred_geology_scalar"] = existing_key
        return meta
    centers = [_cell_center(mesh, cell) for cell in mesh.cells]
    zs = [c[2] for c in centers]
    zmin, zmax = min(zs), max(zs)
    if zmax <= zmin:
        tags = ["layer_00"] * mesh.cell_count
        boundaries = [float(zmin), float(zmax)]
    else:
        layer_count = max(1, min(int(requested_layers), mesh.cell_count, 12))
        step = (zmax - zmin) / float(layer_count)
        tags = []
        for z in zs:
            idx = int((z - zmin) / step) if step > 0 else 0
            idx = max(0, min(layer_count - 1, idx))
            # Higher elevations get smaller labels in common geology UI order.
            tags.append(f"layer_{layer_count - 1 - idx:02d}")
        boundaries = [float(zmin + i * step) for i in range(layer_count + 1)]
    mesh.cell_tags["geology_layer_id"] = tags
    mesh.cell_tags.setdefault("display_group", tags)
    meta = {"layer_count": len(set(tags)), "source": "elevation_bins", "z_boundaries": boundaries, "layers": list(dict.fromkeys(tags))}
    mesh.metadata["geology_layer_display"] = meta
    return meta


@dataclass(slots=True)
class FEMMeshOptimizationReport:
    ok: bool
    node_count_before: int = 0
    node_count_after: int = 0
    cell_count_before: int = 0
    cell_count_after: int = 0
    removed_degenerate_cells: list[int] = field(default_factory=list)
    duplicate_nodes_merged: int = 0
    min_quality: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": FEM_MESH_QUALITY_CONTRACT,
            "ok": bool(self.ok),
            "node_count_before": int(self.node_count_before),
            "node_count_after": int(self.node_count_after),
            "cell_count_before": int(self.cell_count_before),
            "cell_count_after": int(self.cell_count_after),
            "removed_degenerate_cells": list(self.removed_degenerate_cells),
            "duplicate_nodes_merged": int(self.duplicate_nodes_merged),
            "min_quality": self.min_quality,
            "max_aspect_ratio": self.max_aspect_ratio,
            "bad_cell_ids": list(self.bad_cell_ids),
            "warnings": list(self.warnings),
            "actions": list(self.actions),
            "metadata": dict(self.metadata),
        }


def analyze_mesh_for_fem(mesh: MeshDocument | None, *, max_aspect_ratio: float = 20.0, min_measure: float = 1.0e-12) -> FEMMeshOptimizationReport:
    if mesh is None:
        return FEMMeshOptimizationReport(ok=False, warnings=["未加载网格。"], actions=["先导入 MSH/VTU/STL/IFC/STEP 或生成体网格。"])
    bad: list[int] = []
    qualities: list[float] = []
    aspects: list[float] = []
    warnings: list[str] = []
    volume_count = 0
    surface_count = 0
    for i, cell in enumerate(mesh.cells):
        ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "").lower()
        if ctype in _VOLUME_TYPES or len(cell) in {4, 5, 6, 8}:
            volume_count += 1
        if ctype in _SURFACE_TYPES or len(cell) in {3, 4}:
            surface_count += 1
        pts = _cell_points(mesh, cell)
        measure = _cell_measure(mesh, cell, ctype)
        aspect = _aspect_ratio(pts)
        if aspect != float("inf"):
            aspects.append(float(aspect))
        q = 0.0 if measure <= min_measure or aspect == float("inf") else min(1.0, 1.0 / max(1.0, aspect))
        qualities.append(float(q))
        if len(set(int(v) for v in cell)) != len(tuple(cell)) or measure <= min_measure or aspect > max_aspect_ratio:
            bad.append(i)
    if mesh.cell_count == 0:
        warnings.append("网格没有单元。")
    if volume_count == 0 and surface_count > 0:
        warnings.append("当前是表面网格，有限元体分析前需要重新生成体网格。")
    if bad:
        warnings.append(f"发现 {len(bad)} 个疑似坏单元，需要修复或重新网格划分。")
    layer_meta = add_geology_layer_tags(mesh)
    report = FEMMeshOptimizationReport(
        ok=bool(mesh.cell_count and not bad and volume_count > 0),
        node_count_before=mesh.node_count,
        node_count_after=mesh.node_count,
        cell_count_before=mesh.cell_count,
        cell_count_after=mesh.cell_count,
        min_quality=min(qualities) if qualities else None,
        max_aspect_ratio=max(aspects) if aspects else None,
        bad_cell_ids=bad,
        warnings=warnings,
        actions=["已计算 FEM 网格质量指标。", "已补充/刷新地质分层显示标签。"],
        metadata={"volume_cell_count": volume_count, "surface_cell_count": surface_count, "geology_layer_display": layer_meta},
    )
    mesh.quality = MeshQualityReport(min_quality=report.min_quality, max_aspect_ratio=report.max_aspect_ratio, bad_cell_ids=list(bad), warnings=list(warnings))
    mesh.metadata["fem_quality_report"] = report.to_dict()
    return report


def optimize_mesh_for_fem(mesh: MeshDocument | None, *, merge_tolerance: float = 1.0e-9, remove_degenerate: bool = True) -> tuple[MeshDocument | None, FEMMeshOptimizationReport]:
    if mesh is None:
        return None, analyze_mesh_for_fem(None)
    before_nodes = mesh.node_count
    before_cells = mesh.cell_count
    # Compact duplicate nodes by rounded coordinate key.  This is conservative
    # and keeps imported geometry unchanged at engineering display precision.
    key_to_new: dict[tuple[int, int, int], int] = {}
    new_nodes: list[tuple[float, float, float]] = []
    old_to_new: dict[int, int] = {}
    scale = 1.0 / max(float(merge_tolerance), 1.0e-15)
    for idx, p in enumerate(mesh.nodes):
        key = (round(float(p[0]) * scale), round(float(p[1]) * scale), round(float(p[2]) * scale))
        if key not in key_to_new:
            key_to_new[key] = len(new_nodes)
            new_nodes.append((float(p[0]), float(p[1]), float(p[2])))
        old_to_new[idx] = key_to_new[key]
    new_cells: list[tuple[int, ...]] = []
    new_types: list[str] = []
    keep_old_indices: list[int] = []
    removed: list[int] = []
    temp = MeshDocument(nodes=new_nodes, cells=[], cell_types=[])
    for i, cell in enumerate(mesh.cells):
        mapped = tuple(old_to_new.get(int(v), int(v)) for v in cell)
        ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "")
        measure = _cell_measure(temp, mapped, ctype)
        if remove_degenerate and (len(set(mapped)) != len(mapped) or measure <= 1.0e-12):
            removed.append(i)
            continue
        new_cells.append(mapped)
        new_types.append(ctype)
        keep_old_indices.append(i)
    new_tags: dict[str, list[Any]] = {}
    for name, values in mesh.cell_tags.items():
        vals = list(values)
        if len(vals) == before_cells:
            new_tags[name] = [vals[i] for i in keep_old_indices]
        else:
            new_tags[name] = vals
    optimized = MeshDocument(
        nodes=new_nodes,
        cells=new_cells,
        cell_types=new_types,
        cell_tags=new_tags,
        face_tags={k: list(v) for k, v in mesh.face_tags.items()},
        node_tags={k: list(v) for k, v in mesh.node_tags.items()},
        entity_map=mesh.entity_map,
        metadata={**dict(mesh.metadata), "optimized_for_fem": True, "optimization_contract": FEM_MESH_QUALITY_CONTRACT},
    )
    report = analyze_mesh_for_fem(optimized)
    report.node_count_before = before_nodes
    report.node_count_after = optimized.node_count
    report.cell_count_before = before_cells
    report.cell_count_after = optimized.cell_count
    report.removed_degenerate_cells = removed
    report.duplicate_nodes_merged = max(0, before_nodes - optimized.node_count)
    report.actions.insert(0, f"合并重复节点 {report.duplicate_nodes_merged} 个。")
    if removed:
        report.actions.insert(1, f"移除退化单元 {len(removed)} 个。")
    optimized.quality = MeshQualityReport(min_quality=report.min_quality, max_aspect_ratio=report.max_aspect_ratio, bad_cell_ids=list(report.bad_cell_ids), warnings=list(report.warnings))
    optimized.metadata["fem_quality_report"] = report.to_dict()
    return optimized, report



def identify_geological_layers(mesh: MeshDocument | None, *, requested_layers: int = 8) -> dict[str, Any]:
    """Identify geology layers from real cell tags or elevation fallback.

    Priority follows ParaView-style imported attributes: ``soil_id`` first,
    then material/stratum/layer/Gmsh physical tags.  The function writes
    ``geology_layer_id`` and ``display_group`` so visualization and material
    assignment use the same layer model.
    """
    if mesh is None:
        return {"ok": False, "reason": "no_mesh"}
    meta = add_geology_layer_tags(mesh, requested_layers=requested_layers)
    values = list(mesh.cell_tags.get("geology_layer_id", []))
    counts: dict[str, int] = {}
    for v in values:
        counts[str(v)] = counts.get(str(v), 0) + 1
    layers = [{"id": key, "cell_count": count} for key, count in counts.items()]
    mesh.metadata["identified_geology_layers"] = layers
    return {"ok": True, "contract": "geoai_geology_layer_identification_v1", "layer_count": len(layers), "layers": layers, "metadata": meta}


def _faces_for_cell(cell: tuple[int, ...], ctype: str) -> list[tuple[int, ...]]:
    ids = tuple(int(v) for v in cell)
    lower = str(ctype or "").lower()
    if len(ids) == 8 or lower in {"hex8", "hexahedron"}:
        return [
            (ids[0], ids[1], ids[2], ids[3]),
            (ids[4], ids[5], ids[6], ids[7]),
            (ids[0], ids[1], ids[5], ids[4]),
            (ids[1], ids[2], ids[6], ids[5]),
            (ids[2], ids[3], ids[7], ids[6]),
            (ids[3], ids[0], ids[4], ids[7]),
        ]
    if len(ids) == 4 or lower in {"tet4", "tetra"}:
        return [(ids[0], ids[1], ids[2]), (ids[0], ids[1], ids[3]), (ids[1], ids[2], ids[3]), (ids[2], ids[0], ids[3])]
    if len(ids) == 6 or lower in {"wedge", "wedge6"}:
        return [(ids[0], ids[1], ids[2]), (ids[3], ids[4], ids[5]), (ids[0], ids[1], ids[4], ids[3]), (ids[1], ids[2], ids[5], ids[4]), (ids[2], ids[0], ids[3], ids[5])]
    if len(ids) == 5 or lower in {"pyramid", "pyramid5"}:
        return [(ids[0], ids[1], ids[2], ids[3]), (ids[0], ids[1], ids[4]), (ids[1], ids[2], ids[4]), (ids[2], ids[3], ids[4]), (ids[3], ids[0], ids[4])]
    if len(ids) in {3, 4}:
        return [ids]
    return []


def diagnose_nonmanifold_mesh(mesh: MeshDocument | None) -> dict[str, Any]:
    """Diagnose boundary, duplicate and non-manifold topology problems."""
    if mesh is None:
        return {"ok": False, "reason": "no_mesh"}
    face_use: dict[tuple[int, ...], int] = {}
    duplicate_cells = 0
    seen_cells: set[tuple[int, ...]] = set()
    for i, cell in enumerate(mesh.cells):
        ctype = str(mesh.cell_types[i] if i < len(mesh.cell_types) else "")
        normalized_cell = tuple(sorted(int(v) for v in cell))
        if normalized_cell in seen_cells:
            duplicate_cells += 1
        seen_cells.add(normalized_cell)
        for face in _faces_for_cell(tuple(int(v) for v in cell), ctype):
            key = tuple(sorted(int(v) for v in face))
            face_use[key] = face_use.get(key, 0) + 1
    boundary_faces = [f for f, count in face_use.items() if count == 1]
    nonmanifold_faces = [f for f, count in face_use.items() if count > 2]
    report = {
        "ok": len(nonmanifold_faces) == 0 and duplicate_cells == 0,
        "contract": "geoai_mesh_nonmanifold_report_v1",
        "cell_count": mesh.cell_count,
        "node_count": mesh.node_count,
        "boundary_face_count": len(boundary_faces),
        "internal_face_count": sum(1 for count in face_use.values() if count == 2),
        "nonmanifold_face_count": len(nonmanifold_faces),
        "duplicate_cell_count": duplicate_cells,
        "actions": [],
    }
    if nonmanifold_faces:
        report["actions"].append("发现非流形面：建议先检查重复/重叠体单元，必要时用 Gmsh/OCC 重新分区并生成 conformal mesh。")
    if duplicate_cells:
        report["actions"].append("发现重复单元：可执行网格降重/优化移除重复单元。")
    if not report["actions"]:
        report["actions"].append("未发现重复单元或 face-use>2 的非流形面。")
    mesh.metadata["nonmanifold_report"] = report
    return report


def reduce_mesh_weight(mesh: MeshDocument | None, *, merge_tolerance: float = 1.0e-9, remove_duplicate_cells: bool = True) -> tuple[MeshDocument | None, dict[str, Any]]:
    """Conservative mesh weight reduction for imported geology meshes.

    This avoids destructive geometric decimation.  It merges duplicate nodes,
    removes duplicate/degenerate cells, drops unused nodes and preserves all
    geology cell tags for remaining cells.
    """
    if mesh is None:
        return None, {"ok": False, "reason": "no_mesh"}
    optimized, qreport = optimize_mesh_for_fem(mesh, merge_tolerance=merge_tolerance, remove_degenerate=True)
    if optimized is None:
        return None, {"ok": False, "reason": "optimization_failed"}
    keep_indices: list[int] = []
    seen: set[tuple[int, ...]] = set()
    duplicate_removed: list[int] = []
    for i, cell in enumerate(optimized.cells):
        key = tuple(sorted(int(v) for v in cell))
        if remove_duplicate_cells and key in seen:
            duplicate_removed.append(i)
            continue
        seen.add(key)
        keep_indices.append(i)
    if duplicate_removed:
        cells = [optimized.cells[i] for i in keep_indices]
        cell_types = [optimized.cell_types[i] for i in keep_indices]
        cell_tags: dict[str, list[Any]] = {}
        for name, values in optimized.cell_tags.items():
            vals = list(values)
            if len(vals) == optimized.cell_count:
                cell_tags[name] = [vals[i] for i in keep_indices]
            else:
                cell_tags[name] = vals
        optimized = MeshDocument(nodes=list(optimized.nodes), cells=cells, cell_types=cell_types, cell_tags=cell_tags, face_tags=dict(optimized.face_tags), node_tags=dict(optimized.node_tags), entity_map=optimized.entity_map, metadata=dict(optimized.metadata))
    # Remove unused nodes and remap cells.
    used = sorted({int(v) for cell in optimized.cells for v in cell})
    remap = {old: new for new, old in enumerate(used)}
    nodes = [optimized.nodes[i] for i in used]
    cells = [tuple(remap[int(v)] for v in cell) for cell in optimized.cells]
    reduced = MeshDocument(nodes=nodes, cells=cells, cell_types=list(optimized.cell_types), cell_tags={k: list(v) for k, v in optimized.cell_tags.items()}, face_tags=dict(optimized.face_tags), node_tags=dict(optimized.node_tags), entity_map=optimized.entity_map, metadata={**dict(optimized.metadata), "mesh_weight_reduced": True})
    identify_geological_layers(reduced)
    final_report = analyze_mesh_for_fem(reduced)
    nonmanifold = diagnose_nonmanifold_mesh(reduced)
    report = {
        "ok": final_report.ok and nonmanifold.get("nonmanifold_face_count", 0) == 0,
        "contract": "geoai_mesh_weight_reduction_v1",
        "node_count_before": mesh.node_count,
        "node_count_after": reduced.node_count,
        "cell_count_before": mesh.cell_count,
        "cell_count_after": reduced.cell_count,
        "duplicate_nodes_merged": qreport.duplicate_nodes_merged,
        "duplicate_cells_removed": len(duplicate_removed),
        "unused_nodes_removed": max(0, optimized.node_count - reduced.node_count),
        "quality_report": final_report.to_dict(),
        "nonmanifold_report": nonmanifold,
    }
    reduced.metadata["mesh_weight_reduction_report"] = report
    return reduced, report


def analyze_project_mesh_for_fem(project: Any) -> FEMMeshOptimizationReport:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    report = analyze_mesh_for_fem(mesh)
    if mesh is not None:
        try:
            project.mesh_model.quality_report = mesh.quality
            project.mesh_model.metadata["fem_quality_report"] = report.to_dict()
            project.metadata["fem_mesh_quality_report"] = report.to_dict()
        except Exception:
            pass
    return report


def optimize_project_mesh_for_fem(project: Any) -> FEMMeshOptimizationReport:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    optimized, report = optimize_mesh_for_fem(mesh)
    if optimized is not None:
        try:
            project.mesh_model.attach_mesh(optimized)
            project.mesh_model.metadata["fem_quality_report"] = report.to_dict()
            project.metadata["fem_mesh_quality_report"] = report.to_dict()
            project.metadata["dirty"] = True
        except Exception:
            pass
    return report


__all__ = [
    "FEM_MESH_QUALITY_CONTRACT",
    "FEMMeshOptimizationReport",
    "add_geology_layer_tags",
    "analyze_mesh_for_fem",
    "optimize_mesh_for_fem",
    "analyze_project_mesh_for_fem",
    "optimize_project_mesh_for_fem",
    "identify_geological_layers",
    "diagnose_nonmanifold_mesh",
    "reduce_mesh_weight",
]
