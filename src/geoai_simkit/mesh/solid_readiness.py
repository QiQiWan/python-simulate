from __future__ import annotations

"""3D solid-analysis readiness gates for STL and volumetric meshes."""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import (
    SOLID_CELL_TYPES,
    SURFACE_CELL_TYPES,
    SolidAnalysisReadinessIssue,
    SolidAnalysisReadinessReport,
    project_mesh_summary,
)


def _mesh_from(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "nodes") and hasattr(value, "cells"):
        return value
    try:
        return as_project_context(value).current_mesh()
    except Exception:
        return None


def _families(mesh: Any) -> tuple[str, ...]:
    return tuple(sorted({str(item).lower() for item in list(getattr(mesh, "cell_types", []) or [])}))


def validate_solid_analysis_readiness(project_or_mesh: Any) -> SolidAnalysisReadinessReport:
    """Return a structured gate report for 3D solid mechanics.

    The gate intentionally distinguishes STL/surface meshes from solver-ready
    volume meshes. A surface mesh may be valid geometry, but it is not a valid
    solid-mechanics discretization until tetrahedral/hexahedral volume cells are
    present.
    """

    mesh = _mesh_from(project_or_mesh)
    issues: list[SolidAnalysisReadinessIssue] = []
    if mesh is None:
        issues.append(
            SolidAnalysisReadinessIssue(
                severity="error",
                code="mesh.missing",
                message="No mesh is attached; generate a 3D volume mesh before running solid analysis.",
                hint="Run a mesh generator such as voxel_hex8_from_stl or gmsh_tet4_from_stl.",
            )
        )
        return SolidAnalysisReadinessReport(ready=False, issues=tuple(issues))

    metadata = dict(getattr(mesh, "metadata", {}) or {})
    cell_types = [str(item).lower() for item in list(getattr(mesh, "cell_types", []) or [])]
    solid_count = sum(1 for item in cell_types if item in SOLID_CELL_TYPES)
    surface_count = sum(1 for item in cell_types if item in SURFACE_CELL_TYPES)
    cell_count = int(getattr(mesh, "cell_count", len(getattr(mesh, "cells", []) or [])) or 0)
    node_count = int(getattr(mesh, "node_count", len(getattr(mesh, "nodes", []) or [])) or 0)
    cell_families = _families(mesh)
    mesh_role = str(metadata.get("mesh_role") or ("solid_volume" if solid_count else ("geometry_surface" if surface_count else "unknown")))
    mesh_dimension = int(metadata.get("mesh_dimension") or (3 if solid_count else (2 if surface_count else 0)))

    if cell_count <= 0 or node_count <= 0:
        issues.append(
            SolidAnalysisReadinessIssue(
                severity="error",
                code="mesh.empty",
                message="The mesh has no cells or nodes.",
                target="MeshDocument",
            )
        )
    if surface_count and solid_count == 0:
        issues.append(
            SolidAnalysisReadinessIssue(
                severity="error",
                code="mesh.surface_only",
                message="The attached STL mesh contains surface cells only; 3D solid FEM requires Tet4/Hex8 volume cells.",
                target="MeshDocument.cell_types",
                hint="Run volume meshing first: voxel_hex8_from_stl is dependency-light; gmsh_tet4_from_stl can create Tet4 cells when gmsh/meshio are installed.",
                metadata={"surface_cell_count": surface_count, "cell_families": list(cell_families)},
            )
        )
    if solid_count > 0 and mesh_dimension != 3:
        issues.append(
            SolidAnalysisReadinessIssue(
                severity="warning",
                code="mesh.dimension_metadata",
                message="The mesh has solid cells but mesh_dimension metadata is not 3; treating it as a 3D volume mesh.",
                target="MeshDocument.metadata.mesh_dimension",
            )
        )
    unknown_count = cell_count - solid_count - surface_count
    if unknown_count > 0:
        issues.append(
            SolidAnalysisReadinessIssue(
                severity="warning",
                code="mesh.unknown_cell_types",
                message="Some cells have unknown or unsupported cell families and will not be used by the solid solver.",
                target="MeshDocument.cell_types",
                metadata={"unknown_cell_count": unknown_count, "cell_families": list(cell_families)},
            )
        )

    ready = bool(solid_count > 0 and not any(issue.blocking for issue in issues))
    return SolidAnalysisReadinessReport(
        ready=ready,
        mesh_role=mesh_role,
        mesh_dimension=mesh_dimension,
        node_count=node_count,
        cell_count=cell_count,
        solid_cell_count=solid_count,
        surface_cell_count=surface_count,
        cell_families=cell_families,
        issues=tuple(issues),
        metadata={"mesh_metadata": metadata, "project_mesh_summary": project_mesh_summary(project_or_mesh).to_dict() if not hasattr(project_or_mesh, "nodes") else {}},
    )


__all__ = ["validate_solid_analysis_readiness"]
