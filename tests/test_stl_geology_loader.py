from __future__ import annotations

from pathlib import Path

from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, GeometrySource
from geoai_simkit.geoproject import GeoProjectDocument


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


def test_ascii_stl_loader_builds_quality_report(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    mesh = load_stl_geology(stl_path, STLImportOptions(name="tetra", material_id="rock"))
    assert mesh.quality.triangle_count == 4
    assert mesh.quality.vertex_count == 4
    assert mesh.quality.is_manifold
    assert mesh.to_mesh_document(block_id="tetra").cell_count == 4


def test_stl_geometry_source_builds_single_region(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    case = AnalysisCaseSpec(
        "stl-case",
        geometry=GeometrySource(kind="stl_geology", path=str(stl_path), parameters={"name": "geo_surface", "material_id": "rock"}),
    )
    prepared = AnalysisCaseBuilder(case).build()
    assert prepared.model.mesh.n_cells == 4
    assert [r.name for r in prepared.model.region_tags] == ["geo_surface"]
    assert prepared.model.metadata["stl_geology"]["triangle_count"] == 4


def test_geoproject_from_stl_registers_geometry_mesh_and_material(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "geo_surface", "material_id": "rock"})
    assert "geo_surface" in project.geometry_model.volumes
    assert project.mesh_model.mesh_document is not None
    assert project.mesh_model.mesh_document.cell_count == 4
    assert "rock" in project.material_library.soil_materials
