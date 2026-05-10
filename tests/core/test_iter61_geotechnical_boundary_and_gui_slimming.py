from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.controllers import (
    BoundaryConditionActionController,
    GeotechnicalActionController,
    MaterialMappingActionController,
)
from geoai_simkit.contracts import analysis_readiness_summary, solid_mesh_summary
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import fem_solver, meshing
from geoai_simkit.services import build_geotechnical_readiness_report


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
    stl = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl)
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "iter61", "material_id": "soil"})
    meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")
    project.populate_default_framework_content()
    return project


def test_project_port_v2_geotechnical_summaries_are_strict_and_serializable(tmp_path: Path) -> None:
    project = _solid_project(tmp_path)

    mesh = solid_mesh_summary(project)
    readiness = analysis_readiness_summary(project)
    report = build_geotechnical_readiness_report(project)

    assert mesh.solid_solver_ready is True
    assert mesh.volume_cell_count == 1
    assert mesh.to_dict()["cell_families"] == ["tet4"]
    assert readiness.ready is True
    assert report["contract"] == "geotechnical_readiness_v2"
    assert report["ready"] is True
    assert report["material_mapping"]["ok"] is True
    assert report["boundary_conditions"]["has_constraints"] is True
    assert report["loads"]["has_loads"] is True


def test_staged_mohr_coulomb_backend_runs_incremental_boundary_and_writes_metadata(tmp_path: Path) -> None:
    project = _solid_project(tmp_path)

    result = fem_solver.solve_project(
        project,
        backend_preference="staged_mohr_coulomb_cpu",
        settings={"load_increments": 2, "max_iterations": 3, "tolerance": 1.0e-5},
    )

    assert result.ok is True
    assert result.backend_key == "staged_mohr_coulomb_cpu"
    assert result.metadata["contract"] == "staged_mohr_coulomb_boundary_v1"
    report = result.summary.to_dict()
    assert report["algorithm"] == "staged_mohr_coulomb_boundary_v1"
    assert len(report["increments"]) == 2
    assert report["metadata"]["full_consistent_tangent_newton"] is False
    stage = project.result_store.phase_results["initial"]
    assert "cell_plastic_strain" in stage.fields
    assert "nonlinear_solver_boundary" in stage.metadata


def test_gui_slimming_controllers_route_to_services_and_facades(tmp_path: Path) -> None:
    project = _solid_project(tmp_path)

    assert MaterialMappingActionController(project).summary()["ok"] is True
    assert BoundaryConditionActionController(project).summary()["boundary_conditions"]["has_constraints"] is True
    readiness = GeotechnicalActionController(project).readiness()
    assert readiness["ready"] is True


def test_workflow_routes_to_staged_mohr_coulomb_backend(tmp_path: Path) -> None:
    stl = tmp_path / "tetra_workflow.stl"
    _write_ascii_tetra_stl(stl)
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "workflow", "material_id": "soil"})

    report = GeotechnicalActionController(project).run_staged_mohr_coulomb(
        mesh_kind="gmsh_tet4_from_stl",
        load_increments=2,
        max_iterations=3,
    )

    assert report.ok is True
    assert report.artifacts["solve"].backend_key == "staged_mohr_coulomb_cpu"
    assert report.artifacts["solve"].metadata["contract"] == "staged_mohr_coulomb_boundary_v1"
