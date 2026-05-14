from __future__ import annotations

from importlib import import_module
from typing import Any

from .mesh_document import MeshDocument, MeshQualityReport
from .mesh_entity_map import MeshEntityMap
from .tagged_mesher import generate_tagged_preview_mesh
from .solid_readiness import validate_solid_analysis_readiness
from .complete_3d import apply_3d_boundary_tags, build_mesh3d_topology_report, extract_3d_boundary_faces


def __getattr__(name: str) -> Any:
    if name in {"LayeredMeshResult", "generate_layered_volume_mesh"}:
        module = import_module("geoai_simkit.mesh.layered_mesher")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'geoai_simkit.mesh' has no attribute {name!r}")

__all__ = [
    "LayeredMeshResult",
    "MeshDocument",
    "MeshQualityReport",
    "MeshEntityMap",
    "generate_layered_volume_mesh",
    "generate_tagged_preview_mesh",
    "validate_solid_analysis_readiness",
    "apply_3d_boundary_tags",
    "build_mesh3d_topology_report",
    "extract_3d_boundary_faces",
]
from .fem_quality import (
    FEM_MESH_QUALITY_CONTRACT,
    FEMMeshOptimizationReport,
    add_geology_layer_tags,
    analyze_mesh_for_fem,
    optimize_mesh_for_fem,
    analyze_project_mesh_for_fem,
    optimize_project_mesh_for_fem,
)
