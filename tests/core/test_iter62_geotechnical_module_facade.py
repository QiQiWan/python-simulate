from __future__ import annotations

from pathlib import Path

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import geotechnical, meshing


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


def _solid_project(tmp_path: Path) -> GeoProjectDocument:
    stl = tmp_path / "iter62_tetra.stl"
    _write_ascii_tetra_stl(stl)
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "iter62", "material_id": "soil"})
    meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")
    project.populate_default_framework_content()
    return project


def test_geotechnical_module_state_and_readiness_are_serializable(tmp_path: Path) -> None:
    project = _solid_project(tmp_path)

    state = geotechnical.geotechnical_state(project)
    readiness = geotechnical.readiness_report(project)

    assert state["contract"] == "geotechnical_state_v1"
    assert state["solid_mesh"]["solid_solver_ready"] is True
    assert state["analysis_readiness"]["ready"] is True
    assert readiness["contract"] == "geotechnical_readiness_v2"
    assert readiness["ready"] is True


def test_geotechnical_module_runs_staged_workflow(tmp_path: Path) -> None:
    stl = tmp_path / "iter62_workflow.stl"
    _write_ascii_tetra_stl(stl)
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "iter62-workflow", "material_id": "soil"})

    report = geotechnical.run_staged_geotechnical_analysis(
        project,
        mesh_kind="gmsh_tet4_from_stl",
        load_increments=2,
        max_iterations=3,
        metadata={"case": "iter62"},
    )

    assert report.ok is True
    assert report.metadata["solver_backend"] == "staged_mohr_coulomb_cpu"
    assert report.metadata["case"] == "iter62"
    assert report.artifacts["solve"].backend_key == "staged_mohr_coulomb_cpu"
