from __future__ import annotations

"""Headless geometry-kernel service facade.

Implementation lives in :mod:`geoai_simkit.mesh.geometry_kernel_core` so mesh
plugin registration can use it without importing the services package and
creating registry/service circular imports.
"""

from geoai_simkit.mesh.geometry_kernel_core import (
    build_geometry_kernel_report,
    build_soil_layer_volume_mesh,
    build_stratigraphic_surface_volume_mesh,
    geometry_kernel_dependency_status,
    gmsh_meshio_validation_report,
    build_gmsh_occ_fragment_tet4_mesh,
    geometry_operation_log_status,
    local_remesh_volume_mesh_quality,
    normalize_soil_layers,
    optimize_complex_stl_surface_mesh,
    optimize_stl_surface_mesh,
    optimize_volume_mesh_quality,
)

__all__ = [
    "build_geometry_kernel_report",
    "build_soil_layer_volume_mesh",
    "build_stratigraphic_surface_volume_mesh",
    "geometry_kernel_dependency_status",
    "gmsh_meshio_validation_report",
    "build_gmsh_occ_fragment_tet4_mesh",
    "geometry_operation_log_status",
    "local_remesh_volume_mesh_quality",
    "normalize_soil_layers",
    "optimize_complex_stl_surface_mesh",
    "optimize_stl_surface_mesh",
    "optimize_volume_mesh_quality",
]
