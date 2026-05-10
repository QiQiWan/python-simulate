from __future__ import annotations

from pathlib import Path

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import fem_solver, meshing
from geoai_simkit.services import run_project_workflow


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


def test_solid_linear_static_cpu_rejects_surface_only_stl(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "surface-only", "material_id": "rock"})

    result = fem_solver.solve_project(project, backend_preference="solid_linear_static_cpu")

    assert result.ok is False
    assert result.backend_key == "solid_linear_static_cpu"
    assert result.status == "rejected"
    assert result.metadata["solid_readiness"]["blocking_issues"][0]["code"] == "mesh.surface_only"


def test_solid_linear_static_cpu_solves_imported_tet4_project_and_writes_core_fields(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "tet4-solid", "material_id": "rock"})
    meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")

    result = fem_solver.solve_project(project, backend_preference="solid_linear_static_cpu")

    assert result.ok is True
    assert result.backend_key == "solid_linear_static_cpu"
    assert result.metadata["contract"] == "solid_linear_static_project_v1"
    assert result.phase_records[0].active_cell_count == 1
    assert result.phase_records[0].max_reaction_force > 0.0
    stage = project.result_store.phase_results["initial"]
    for field_name in ["displacement", "ux", "uy", "uz", "reaction_force", "cell_stress", "cell_strain", "cell_von_mises"]:
        assert field_name in stage.fields
    assert stage.fields["cell_stress"].components == 6
    assert stage.fields["cell_strain"].components == 6
    assert stage.fields["reaction_force"].components == 3
    assert stage.metrics["active_cell_count"] == 1.0
    assert stage.metrics["max_reaction_force"] > 0.0


def test_canonical_workflow_routes_stl_volume_mesh_to_project_solid_backend(tmp_path: Path) -> None:
    stl_path = tmp_path / "tetra.stl"
    _write_ascii_tetra_stl(stl_path)
    project = GeoProjectDocument.from_stl_geology(stl_path, options={"name": "workflow-solid", "material_id": "rock"})

    report = run_project_workflow(
        project,
        mesh_kind="gmsh_tet4_from_stl",
        solver_backend="solid_linear_static_cpu",
        summarize=True,
    )

    assert report.ok is True
    assert report.artifacts["solve"].backend_key == "solid_linear_static_cpu"
    assert report.artifacts["solve"].metadata["solid_readiness"]["ready"] is True
    assert report.snapshot_after.result_stage_count >= 1
    assert [step.key for step in report.steps] == ["project_port", "meshing", "stage_planning", "fem_solver", "postprocessing"]
