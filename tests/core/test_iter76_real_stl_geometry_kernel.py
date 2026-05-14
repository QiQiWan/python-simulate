from __future__ import annotations

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.mesh.mesh_document import MeshDocument
from geoai_simkit.modules import meshing
from geoai_simkit.services import run_project_workflow


def _attach(project: GeoProjectDocument, mesh: MeshDocument) -> GeoProjectDocument:
    project.mesh_model.attach_mesh(mesh)
    return project


def _surface_project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_empty(name="strat-surfaces")
    nodes = [
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0), (1.0, 0.0, 1.1), (1.0, 1.0, 1.0), (0.0, 1.0, 0.9),
    ]
    cells = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6)]
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=["tri3"] * 4,
        cell_tags={
            "surface_id": ["bottom", "bottom", "top", "top"],
            "region_name": ["bottom", "bottom", "top", "top"],
            "block_id": ["bottom", "bottom", "top", "top"],
            "material_id": ["soil", "soil", "soil", "soil"],
            "role": ["stratigraphic_surface"] * 4,
        },
        metadata={"mesh_role": "geometry_surface", "requires_volume_meshing": True},
    )
    return _attach(project, mesh)


def test_complex_stl_optimizer_fills_small_hole_and_reports_physical_groups() -> None:
    project = GeoProjectDocument.create_empty(name="hole-patch")
    mesh = MeshDocument(
        nodes=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        cells=[(0, 1, 2), (0, 2, 3)],
        cell_types=["tri3", "tri3"],
        cell_tags={"surface_id": ["ground", "ground"], "region_name": ["ground", "ground"], "material_id": ["soil", "soil"], "role": ["stl_surface", "stl_surface"]},
        metadata={"mesh_role": "geometry_surface"},
    )
    _attach(project, mesh)
    report = meshing.optimize_project_complex_stl_surface(project, fill_holes=True, max_hole_edges=8, attach=True)
    assert report["metadata"]["contract_version"] == "stl_optimization_report_v2"
    assert report["metadata"]["filled_hole_face_count"] >= 3
    assert report["closed"] is True

    gmsh_report = meshing.gmsh_meshio_validation(project)
    assert gmsh_report["metadata"]["contract"] == "gmsh_meshio_validation_report_v1"
    assert gmsh_report["physical_groups"]


def test_stratigraphic_surface_volume_mesh_uses_real_surface_tags_and_preserves_materials() -> None:
    project = _surface_project()
    report = meshing.generate_stratigraphic_surface_volume_mesh(
        project,
        layers=[{"layer_id": "upper_fill", "bottom_surface_id": "bottom", "top_surface_id": "top", "material_id": "fill"}],
        dims=(2, 2),
        element_family="hex8",
    )
    assert report["ok"] is True
    assert report["generated_cell_count"] == 4
    assert report["surface_ids"] == ["bottom", "top"]
    assert report["physical_groups"][0]["name"] == "upper_fill"

    complete = meshing.complete_3d_mesh_report(project)
    assert complete["ok"] is True
    assert complete["topology"]["solid_cell_count"] == 4
    assert "external" in project.mesh_model.mesh_document.face_tags["boundary_sets"]


def test_stratigraphic_surface_generator_and_workflow_geometry_kernel_artifact() -> None:
    project = _surface_project()
    workflow = run_project_workflow(
        project,
        mesh_kind="stratigraphic_surface_volume_from_stl",
        compile_stages=False,
        solve=False,
        summarize=False,
        metadata={
            "mesh_options": {
                "layers": [{"layer_id": "layer_a", "bottom_surface_id": "bottom", "top_surface_id": "top", "material_id": "mat_a"}],
                "dims": (1, 1),
                "element_family": "tet4",
            },
            "include_geometry_kernel_artifact": True,
        },
    )
    assert workflow.ok
    assert workflow.artifact_ref("geometry_kernel") is not None
    assert workflow.artifact_ref("mesh3d") is not None
    mesh = project.mesh_model.mesh_document
    assert mesh.metadata["geometry_kernel"] == "stratigraphic_surface_closure_v1"
    assert set(mesh.cell_types) == {"tet4"}


def test_volume_mesh_quality_optimizer_removes_bad_cells() -> None:
    project = GeoProjectDocument.create_empty(name="bad-cell")
    mesh = MeshDocument(
        nodes=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)],
        cells=[(0, 1, 2, 3), (0, 1, 2, 4)],
        cell_types=["tet4", "tet4"],
        cell_tags={"block_id": ["bad", "good"], "region_name": ["bad", "good"], "material_id": ["soil", "soil"], "role": ["solid_volume", "solid_volume"]},
        metadata={"mesh_role": "solid_volume", "solid_solver_ready": True},
    )
    _attach(project, mesh)
    report = meshing.optimize_project_volume_mesh_quality(project, min_volume=1.0e-12, attach=True)
    assert report["removed_bad_cell_count"] == 1
    assert report["optimized_cell_count"] == 1
    assert project.mesh_model.mesh_document.cell_count == 1
