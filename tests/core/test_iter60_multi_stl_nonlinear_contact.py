from __future__ import annotations

from pathlib import Path

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import fem_solver, geology_import, meshing
from geoai_simkit.services import run_project_workflow


def _write_ascii_tetra_stl(path: Path, *, dx: float = 0.0, name: str = "tetra") -> None:
    def p(x: float, y: float, z: float) -> str:
        return f"{x + dx:g} {y:g} {z:g}"
    path.write_text(
        f"""
solid {name}
facet normal 0 0 1
 outer loop
  vertex {p(0, 0, 0)}
  vertex {p(1, 0, 0)}
  vertex {p(0, 1, 0)}
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex {p(0, 0, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(1, 0, 0)}
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex {p(1, 0, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(0, 1, 0)}
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex {p(0, 1, 0)}
  vertex {p(0, 0, 1)}
  vertex {p(0, 0, 0)}
 endloop
endfacet
endsolid {name}
""".strip(),
        encoding="utf-8",
    )


def test_multi_stl_incremental_import_preserves_regions_and_materials(tmp_path: Path) -> None:
    a = tmp_path / "region_a.stl"
    b = tmp_path / "region_b.stl"
    _write_ascii_tetra_stl(a, dx=0.0, name="region_a")
    _write_ascii_tetra_stl(b, dx=1.0, name="region_b")

    project = GeoProjectDocument.from_stl_geology(a, options={"name": "multi", "material_id": "clay"})
    geology_import.import_stl_into_project(project, b, {"name": "region_b", "material_id": "sand"})

    closure = meshing.diagnose_multi_stl_closure(project)
    mapping = meshing.audit_region_material_mapping(project)

    assert closure["ready"] is True
    assert closure["region_count"] == 2
    assert set(mapping["material_ids"]) == {"clay", "sand"}
    assert mapping["ok"] is True
    assert project.mesh_model.mesh_document.metadata["mesh_kind"] == "multi_stl_tri_surface"


def test_conformal_multi_stl_tet4_generator_outputs_multi_material_solid_and_interfaces(tmp_path: Path) -> None:
    a = tmp_path / "region_a.stl"
    b = tmp_path / "region_b.stl"
    _write_ascii_tetra_stl(a, dx=0.0, name="region_a")
    _write_ascii_tetra_stl(b, dx=1.0, name="region_b")
    project = GeoProjectDocument.from_stl_geology(a, options={"name": "multi", "material_id": "clay"})
    geology_import.import_stl_into_project(project, b, {"name": "region_b", "material_id": "sand"})

    result = meshing.generate_project_mesh(project, mesh_kind="conformal_tet4_from_stl_regions")
    readiness = meshing.validate_solid_analysis_readiness(project)
    contact = meshing.validate_interface_contact_readiness(project)

    assert result.ok is True
    assert readiness.ready is True
    assert result.mesh.cell_types == ["tet4", "tet4"]
    assert set(result.mesh.cell_tags["material_id"]) == {"clay", "sand"}
    assert result.mesh.metadata["conformal"] is True
    assert contact["ready"] is True
    assert contact["interface_count"] >= 1


def test_nonlinear_mohr_coulomb_backend_writes_plasticity_fields(tmp_path: Path) -> None:
    stl = tmp_path / "region.stl"
    _write_ascii_tetra_stl(stl)
    project = GeoProjectDocument.from_stl_geology(stl, options={"name": "nonlinear", "material_id": "soil"})
    meshing.generate_project_mesh(project, mesh_kind="gmsh_tet4_from_stl")

    result = fem_solver.solve_project(project, backend_preference="nonlinear_mohr_coulomb_cpu")

    assert result.ok is True
    assert result.backend_key == "nonlinear_mohr_coulomb_cpu"
    assert result.metadata["contract"] == "nonlinear_mohr_coulomb_preview_v1"
    stage = project.result_store.phase_results["initial"]
    for field in ["cell_plastic_strain", "cell_mohr_coulomb_stress", "cell_yielded", "cell_yield_margin", "cell_plastic_multiplier"]:
        assert field in stage.fields
    assert "yielded_cell_fraction" in stage.metrics
    assert result.metadata["nonlinear_report"]["engineering_level"] == "material_update_preview_not_full_global_newton"


def test_workflow_runs_conformal_multi_stl_with_nonlinear_backend(tmp_path: Path) -> None:
    a = tmp_path / "region_a.stl"
    b = tmp_path / "region_b.stl"
    _write_ascii_tetra_stl(a, dx=0.0, name="region_a")
    _write_ascii_tetra_stl(b, dx=1.0, name="region_b")
    project = GeoProjectDocument.from_stl_geology(a, options={"name": "workflow", "material_id": "clay"})
    geology_import.import_stl_into_project(project, b, {"name": "region_b", "material_id": "sand"})

    report = run_project_workflow(
        project,
        mesh_kind="conformal_tet4_from_stl_regions",
        solver_backend="nonlinear_mohr_coulomb_cpu",
        summarize=True,
    )

    assert report.ok is True
    assert report.artifacts["mesh"].mesh.metadata["region_count"] == 2
    assert report.artifacts["solve"].backend_key == "nonlinear_mohr_coulomb_cpu"
    assert report.snapshot_after.result_stage_count >= 1
