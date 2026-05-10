from __future__ import annotations

"""Production meshing validation service for 3D geotechnical workflows.

This service consolidates optional mesher dependency health, STL shell repair
readiness, region quality, material compatibility and interface conformity.  It
is intentionally headless and does not import Gmsh, meshio, GUI or solver
runtime implementations directly.
"""

import importlib.util
from math import dist
from typing import Any, Iterable

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import (
    InterfaceConformityReport,
    OptionalMesherDependencyStatus,
    ProductionMeshingValidationReport,
    RegionMeshQualitySummary,
    SOLID_CELL_TYPES,
    STLRepairAction,
    STLRepairReport,
)
from geoai_simkit.mesh.multi_region_stl import diagnose_multi_stl_closure
from geoai_simkit.services.quality_gates import evaluate_material_compatibility, evaluate_mesh_quality_gate


def optional_mesher_dependency_status() -> OptionalMesherDependencyStatus:
    """Return dependency health for production conformal Tet4 meshing."""

    gmsh = importlib.util.find_spec("gmsh") is not None
    meshio = importlib.util.find_spec("meshio") is not None
    diagnostics: list[str] = []
    if not gmsh:
        diagnostics.append("gmsh is not installed; general conformal Tet4 STL volume meshing is unavailable.")
    if not meshio:
        diagnostics.append("meshio is not installed; Gmsh mesh conversion/inspection is unavailable.")
    status = "available" if gmsh and meshio else "missing_optional_dependency"
    return OptionalMesherDependencyStatus(
        gmsh_available=gmsh,
        meshio_available=meshio,
        status=status,
        diagnostics=tuple(diagnostics),
        metadata={"entrypoint": "production_meshing_validation", "dependency_group": "meshing"},
    )


def _mesh(project_or_port: Any) -> Any:
    return as_project_context(project_or_port).current_mesh()


def _project(project_or_port: Any) -> Any:
    return as_project_context(project_or_port).get_project()


def _surface_cell_ids(mesh: Any) -> list[int]:
    cell_types = [str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])]
    return [idx for idx, cell_type in enumerate(cell_types) if cell_type in {"tri3", "quad4", "line2"}]


def _edge_counts(mesh: Any, cell_ids: Iterable[int]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for cid in cell_ids:
        cell = tuple(int(v) for v in mesh.cells[int(cid)])
        if len(cell) < 3:
            continue
        if len(cell) == 3:
            edges = ((cell[0], cell[1]), (cell[1], cell[2]), (cell[2], cell[0]))
        else:
            edges = tuple((cell[i], cell[(i + 1) % len(cell)]) for i in range(len(cell)))
        for a, b in edges:
            key = (min(int(a), int(b)), max(int(a), int(b)))
            counts[key] = counts.get(key, 0) + 1
    return counts


def _tri_area(mesh: Any, cell: tuple[int, ...]) -> float:
    if len(cell) < 3:
        return 0.0
    try:
        a, b, c = [tuple(float(v) for v in mesh.nodes[int(i)]) for i in cell[:3]]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
        return (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5 / 2.0
    except Exception:
        return 0.0


def _duplicate_node_count(mesh: Any, *, digits: int = 10) -> int:
    seen: set[tuple[float, float, float]] = set()
    duplicates = 0
    for row in list(getattr(mesh, "nodes", []) or []):
        key = tuple(round(float(v), digits) for v in row[:3])
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def analyze_stl_repair_readiness(project_or_port: Any) -> STLRepairReport:
    """Diagnose STL shell issues that block production volume meshing."""

    mesh = _mesh(project_or_port)
    if mesh is None:
        return STLRepairReport(
            ok=False,
            repairable=False,
            actions=(STLRepairAction("mesh.missing", "No STL/surface mesh is attached to the project.", "error"),),
            metadata={"reason": "missing_mesh"},
        )
    surface_ids = _surface_cell_ids(mesh)
    if not surface_ids:
        return STLRepairReport(
            ok=True,
            repairable=True,
            region_count=0,
            actions=(STLRepairAction("stl.not_surface_input", "Current mesh is already a volume mesh or contains no STL surface cells.", "info"),),
            metadata={"surface_cell_count": 0, "mesh_role": str(getattr(mesh, "metadata", {}).get("mesh_role", ""))},
        )
    edge_counts = _edge_counts(mesh, surface_ids)
    boundary_edges = sum(1 for count in edge_counts.values() if count == 1)
    nonmanifold_edges = sum(1 for count in edge_counts.values() if count > 2)
    duplicate_nodes = _duplicate_node_count(mesh)
    degenerate = sum(1 for cid in surface_ids if _tri_area(mesh, tuple(int(v) for v in mesh.cells[cid])) <= 1.0e-14)
    closure = diagnose_multi_stl_closure(mesh)
    closure_dict = closure.to_dict()
    actions: list[STLRepairAction] = []
    if duplicate_nodes:
        actions.append(STLRepairAction("stl.duplicate_vertices", "Merge duplicate/coincident STL vertices before conformal meshing.", "warning", metadata={"duplicate_node_count": duplicate_nodes}))
    if degenerate:
        actions.append(STLRepairAction("stl.degenerate_faces", "Remove zero-area or degenerate STL facets.", "error", metadata={"degenerate_face_count": degenerate}))
    if boundary_edges:
        actions.append(STLRepairAction("stl.open_boundary", "Close STL holes/open boundary loops before production Tet4 meshing.", "error", metadata={"open_boundary_edge_count": boundary_edges}))
    if nonmanifold_edges:
        actions.append(STLRepairAction("stl.nonmanifold_edges", "Repair non-manifold STL edges before production Tet4 meshing.", "error", metadata={"nonmanifold_edge_count": nonmanifold_edges}))
    if not boundary_edges and not nonmanifold_edges and not degenerate:
        actions.append(STLRepairAction("stl.closed_manifold", "STL surface appears closed/manifold under dependency-light checks.", "info"))
    interface_candidates = list((closure_dict.get("metadata") or {}).get("interface_candidates") or [])
    ok = bool(surface_ids and boundary_edges == 0 and nonmanifold_edges == 0 and degenerate == 0)
    return STLRepairReport(
        ok=ok,
        repairable=True,
        region_count=int(closure.region_count),
        closed_region_count=int(closure.closed_region_count),
        open_boundary_edge_count=int(boundary_edges),
        nonmanifold_edge_count=int(nonmanifold_edges),
        duplicate_node_count=int(duplicate_nodes),
        degenerate_face_count=int(degenerate),
        self_intersection_candidate_count=0,
        actions=tuple(actions),
        metadata={"closure_report": closure_dict, "surface_cell_count": len(surface_ids), "interface_candidate_count": len(interface_candidates)},
    )


def _volume_for_tet(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float | None:
    if len(cell) < 4:
        return None
    try:
        a, b, c, d = [points[int(idx)] for idx in cell[:4]]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        ad = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
        cross = (ac[1] * ad[2] - ac[2] * ad[1], ac[2] * ad[0] - ac[0] * ad[2], ac[0] * ad[1] - ac[1] * ad[0])
        return abs(ab[0] * cross[0] + ab[1] * cross[1] + ab[2] * cross[2]) / 6.0
    except Exception:
        return None


def _aspect(points: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float | None:
    try:
        rows = [points[int(idx)] for idx in cell]
    except Exception:
        return None
    lengths = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            value = float(dist(a, b))
            if value > 0.0:
                lengths.append(value)
    if not lengths:
        return None
    return max(lengths) / max(min(lengths), 1.0e-30)


def build_region_mesh_quality_summary(project_or_port: Any, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 100.0) -> tuple[RegionMeshQualitySummary, ...]:
    """Return per-region quality summaries for solid cells."""

    mesh = _mesh(project_or_port)
    if mesh is None:
        return ()
    points = [tuple(float(v) for v in row) for row in list(getattr(mesh, "nodes", []) or [])]
    cells = [tuple(int(v) for v in cell) for cell in list(getattr(mesh, "cells", []) or [])]
    types = [str(v).lower() for v in list(getattr(mesh, "cell_types", []) or [])]
    regions = list(getattr(mesh, "cell_tags", {}).get("region_name") or getattr(mesh, "cell_tags", {}).get("block_id") or [])
    materials = list(getattr(mesh, "cell_tags", {}).get("material_id") or [])
    grouped: dict[str, dict[str, object]] = {}
    for idx, cell in enumerate(cells):
        ctype = types[idx] if idx < len(types) else "unknown"
        if ctype not in SOLID_CELL_TYPES:
            continue
        region = str(regions[idx] if idx < len(regions) else "region")
        material = str(materials[idx] if idx < len(materials) else "")
        row = grouped.setdefault(region, {"material_id": material, "volumes": [], "aspects": [], "bad": 0, "count": 0})
        row["count"] = int(row["count"]) + 1
        if not row.get("material_id"):
            row["material_id"] = material
        volume = _volume_for_tet(points, cell) if ctype.startswith("tet") else None
        aspect = _aspect(points, cell)
        if volume is not None:
            row["volumes"].append(float(volume))  # type: ignore[union-attr]
        if aspect is not None:
            row["aspects"].append(float(aspect))  # type: ignore[union-attr]
        if volume is None or volume <= min_volume or (aspect is not None and aspect > max_aspect_ratio):
            row["bad"] = int(row["bad"]) + 1
    summaries = []
    for region, row in sorted(grouped.items()):
        vols = list(row.get("volumes") or [])
        aspects = list(row.get("aspects") or [])
        summaries.append(
            RegionMeshQualitySummary(
                region_id=region,
                material_id=str(row.get("material_id") or ""),
                cell_count=int(row.get("count") or 0),
                min_volume=min(vols) if vols else None,
                max_aspect_ratio=max(aspects) if aspects else None,
                bad_cell_count=int(row.get("bad") or 0),
                metadata={"min_volume_threshold": min_volume, "max_aspect_ratio_threshold": max_aspect_ratio},
            )
        )
    return tuple(summaries)


def validate_interface_conformity(project_or_port: Any) -> InterfaceConformityReport:
    """Validate whether multi-region interfaces are present and materialized."""

    mesh = _mesh(project_or_port)
    if mesh is None:
        return InterfaceConformityReport(ok=True, diagnostics=("No mesh attached; interface conformity not applicable.",))
    metadata = dict(getattr(mesh, "metadata", {}) or {})
    face_tags = dict(getattr(mesh, "face_tags", {}) or {})
    candidates = list(face_tags.get("interface_candidates") or metadata.get("interface_candidates") or [])
    project = _project(project_or_port)
    mesh_model = getattr(project, "mesh_model", None)
    materialized = dict(getattr(mesh_model, "metadata", {}) or {}).get("interface_materialization") if mesh_model is not None else None
    diagnostics: list[str] = []
    missing = 0
    if candidates and not materialized:
        missing = len(candidates)
        diagnostics.append("Interface candidates exist but no interface materialization metadata was found.")
    if materialized and isinstance(materialized, dict) and materialized.get("ok") is False:
        diagnostics.append(str(materialized.get("error", "Interface materialization reported failure.")))
    ok = bool(not candidates or (materialized and isinstance(materialized, dict) and materialized.get("ok", True) is not False))
    return InterfaceConformityReport(
        ok=ok,
        candidate_count=len(candidates),
        conformal_pair_count=len(candidates) if ok else 0,
        nonconformal_pair_count=0 if ok else len(candidates),
        missing_interface_material_count=missing,
        diagnostics=tuple(diagnostics),
        metadata={"interface_materialization": materialized or {}, "source": "mesh.face_tags.interface_candidates"},
    )


def build_production_meshing_validation_report(project_or_port: Any, *, solver_backend: str = "solid_linear_static_cpu") -> ProductionMeshingValidationReport:
    """Aggregate production mesh validation gates for workflow/reporting layers."""

    deps = optional_mesher_dependency_status()
    repair = analyze_stl_repair_readiness(project_or_port)
    mesh_quality = evaluate_mesh_quality_gate(project_or_port).to_dict()
    material = evaluate_material_compatibility(project_or_port, solver_backend=solver_backend).to_dict()
    interfaces = validate_interface_conformity(project_or_port)
    region_quality = build_region_mesh_quality_summary(project_or_port)
    mesh_ok = bool(mesh_quality.get("ok", False))
    material_ok = bool(material.get("ok", False))
    region_ok = all(item.ok for item in region_quality) if region_quality else mesh_ok
    ok = bool(mesh_ok and material_ok and interfaces.ok and region_ok)
    return ProductionMeshingValidationReport(
        ok=ok,
        dependency_status=deps,
        stl_repair=repair,
        mesh_quality=mesh_quality,
        material_compatibility=material,
        interface_conformity=interfaces,
        region_quality=region_quality,
        metadata={"solver_backend": solver_backend, "contract_version": "production_meshing_validation_report_v1"},
    )


__all__ = [
    "analyze_stl_repair_readiness",
    "build_production_meshing_validation_report",
    "build_region_mesh_quality_summary",
    "optional_mesher_dependency_status",
    "validate_interface_conformity",
]
