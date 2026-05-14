from __future__ import annotations

from tempfile import mkdtemp

from geoai_simkit.examples.verified_3d import write_tetra_stl
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import meshing
from geoai_simkit.services import run_project_workflow


def _project() -> GeoProjectDocument:
    root = mkdtemp(prefix="geoai-kernel-")
    path = write_tetra_stl(f"{root}/tetra.stl", name="kernel_tetra")
    return GeoProjectDocument.from_stl_geology(path, options={"name": "kernel-tetra", "material_id": "clay"})


def test_geometry_kernel_dependency_status_and_stl_optimization_report() -> None:
    project = _project()
    status = meshing.geometry_kernel_dependency_status()
    assert status["metadata"]["contract"] == "geometry_kernel_dependency_status_v1"
    assert "production_tet4_available" in status

    report = meshing.geometry_kernel_report(project)
    assert report["metadata"]["contract"] == "geometry_kernel_report_v1"
    assert report["stl_optimization"]["closed"] is True
    assert report["stl_optimization"]["manifold"] is True

    optimized = meshing.optimize_project_stl_surface(project, attach=True)
    assert optimized["ok"] is True
    assert optimized["attached"] is True
    assert optimized["optimized_face_count"] == 4


def test_soil_layer_cut_generates_materialized_3d_volume_mesh() -> None:
    project = _project()
    layers = [
        {"layer_id": "upper_clay", "z_min": 0.0, "z_max": 0.5, "material_id": "clay"},
        {"layer_id": "lower_sand", "z_min": 0.5, "z_max": 1.0, "material_id": "sand"},
    ]
    report = meshing.generate_soil_layer_volume_mesh(project, layers=layers, dims=(1, 1), element_family="hex8")
    assert report["ok"] is True
    assert report["layer_count"] == 2
    assert report["generated_cell_count"] == 2
    assert set(report["material_ids"]) == {"clay", "sand"}

    complete = meshing.complete_3d_mesh_report(project)
    assert complete["ok"] is True
    assert complete["topology"]["solid_cell_count"] == 2
    assert complete["topology"]["interface_pairs"]


def test_soil_layered_volume_generator_and_workflow_artifact() -> None:
    project = _project()
    layers = [
        {"layer_id": "upper", "z_min": 0.0, "z_max": 0.5, "material_id": "clay"},
        {"layer_id": "lower", "z_min": 0.5, "z_max": 1.0, "material_id": "sand"},
    ]
    result = meshing.generate_project_mesh(
        project,
        mesh_kind="soil_layered_volume_from_stl",
        options={"layers": layers, "dims": (1, 1), "element_family": "tet4"},
    )
    assert result.ok
    assert result.mesh.metadata["geometry_kernel"] == "soil_layer_cut_v1"
    assert result.mesh.cell_count == 10

    workflow_project = _project()
    workflow = run_project_workflow(
        workflow_project,
        mesh_kind="soil_layered_volume_from_stl",
        compile_stages=False,
        solve=False,
        summarize=False,
        metadata={"include_geometry_kernel_artifact": True, "mesh_options": {"layers": layers, "dims": (1, 1)}},
    )
    assert workflow.ok
    assert workflow.artifact_ref("geometry_kernel") is not None
    assert workflow.artifact_ref("mesh3d") is not None
    assert "geometry_kernel" in workflow.artifacts


def test_supported_generators_include_soil_layered_volume_from_stl() -> None:
    assert "soil_layered_volume_from_stl" in meshing.supported_mesh_generators()
    assert "soil_layered_volume_from_stl" in meshing.supported_3d_mesh_generators()
