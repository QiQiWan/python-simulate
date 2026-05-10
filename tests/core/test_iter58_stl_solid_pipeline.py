from __future__ import annotations

from pathlib import Path

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import fem_solver, meshing


def _write_ascii_tetra_stl(path: Path) -> None:
    path.write_text(
        """
solid tetra
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex 0 0 0
  vertex 0 0 1
  vertex 1 0 0
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex 1 0 0
  vertex 0 0 1
  vertex 0 1 0
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex 0 1 0
  vertex 0 0 1
  vertex 0 0 0
 endloop
endfacet
endsolid tetra
""".strip(),
        encoding="utf-8",
    )


def test_stl_import_is_surface_geometry_not_solid_solver_ready(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "geo_surface", "material_id": "rock"})

    mesh_summary = meshing.current_project_mesh_summary(project)
    readiness = meshing.validate_solid_analysis_readiness(project)

    assert mesh_summary["mesh_role"] == "geometry_surface"
    assert mesh_summary["requires_volume_meshing"] is True
    assert mesh_summary["solid_solver_ready"] is False
    assert readiness.ready is False
    assert readiness.blocking_issues[0].code == "mesh.surface_only"

    compiled = project.compile_phase_models()
    assert all(row.active_cell_count == 0 for row in compiled.values())

    solve_result = fem_solver.solve_project(project)
    assert solve_result.ok is False
    assert solve_result.status == "rejected"
    assert solve_result.metadata["solid_readiness"]["blocking_issues"][0]["code"] == "mesh.surface_only"


def test_gmsh_tet4_from_stl_simple_tetra_fallback_produces_solid_mesh(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "geo_surface", "material_id": "rock"})

    result = meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")
    readiness = meshing.validate_solid_analysis_readiness(project)

    assert result.ok is True
    assert result.mesh.cell_types == ["tet4"]
    assert readiness.ready is True
    assert readiness.solid_cell_count == 1
    assert meshing.current_project_mesh_summary(project)["mesh_role"] == "solid_volume"


def test_voxel_hex8_from_stl_produces_dependency_light_solid_mesh(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "geo_surface", "material_id": "rock"})

    result = meshing.generate_project_mesh(project, mesh_kind="voxel_hex8_from_stl", options={"dims": (1, 1, 1)})
    readiness = meshing.validate_solid_analysis_readiness(project)

    assert result.ok is True
    assert result.mesh.cell_types == ["hex8"]
    assert readiness.ready is True
    assert readiness.solid_cell_count == 1
    assert "voxel_hex8_from_stl" in meshing.supported_mesh_generators()
    assert "gmsh_tet4_from_stl" in meshing.supported_mesh_generators()
