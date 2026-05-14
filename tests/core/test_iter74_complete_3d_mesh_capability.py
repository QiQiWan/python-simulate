from __future__ import annotations

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules import meshing
from geoai_simkit.services import build_complete_3d_mesh_report, run_project_workflow, supported_3d_mesh_generators


def test_structured_hex8_box_mesh_has_complete_boundary_sets() -> None:
    project = GeoProjectDocument.create_empty(name="hex8-complete-3d")
    result = meshing.generate_project_mesh(
        project,
        mesh_kind="structured_hex8_box",
        options={"dims": (2, 1, 1), "bounds": (0, 2, 0, 1, 0, 1), "material_id": "rock", "region_name": "rock_mass"},
    )
    assert result.ok
    assert result.mesh.cell_count == 2
    assert result.mesh.metadata["mesh_role"] == "solid_volume"
    assert result.mesh.metadata["complete_3d_mesh"] is True
    assert set(result.mesh.face_tags["boundary_sets"]) >= {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}

    report = meshing.complete_3d_mesh_report(project)
    assert report["ok"] is True
    assert report["topology"]["solid_cell_count"] == 2
    assert report["topology"]["boundary_face_count"] == 10
    assert report["topology"]["internal_face_count"] == 1
    assert report["topology"]["regions"][0]["material_id"] == "rock"


def test_structured_tet4_box_mesh_is_solver_ready_and_tagged() -> None:
    project = GeoProjectDocument.create_empty(name="tet4-complete-3d")
    result = meshing.generate_project_mesh(
        project,
        mesh_kind="structured_tet4_box",
        options={"dims": (1, 1, 1), "material_id": "clay", "region_name": "clay_core"},
    )
    assert result.ok
    assert result.mesh.cell_count == 5
    readiness = meshing.validate_solid_analysis_readiness(project).to_dict()
    assert readiness["ready"] is True
    faces = meshing.project_3d_boundary_faces(project)
    assert faces
    assert {row["boundary_set"] for row in faces} >= {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}


def test_complete_3d_mesh_report_service_and_workflow_artifact() -> None:
    project = GeoProjectDocument.create_empty(name="workflow-complete-3d")
    workflow = run_project_workflow(
        project,
        mesh_kind="structured_hex8_box",
        compile_stages=False,
        solve=False,
        summarize=False,
        metadata={"include_complete_3d_mesh_artifact": True, "workflow_id": "complete_3d_mesh_workflow"},
    )
    assert workflow.ok
    assert "mesh3d" in workflow.artifacts
    assert workflow.artifact_ref("mesh3d") is not None
    manifest = workflow.artifact_manifest().to_dict()
    assert any(row["key"] == "mesh3d" for row in manifest["artifacts"])

    report = build_complete_3d_mesh_report(project).to_dict()
    assert report["ok"] is True
    assert "structured_hex8_box" in report["supported_generators"]
    assert "structured_tet4_box" in report["supported_generators"]


def test_supported_3d_mesh_generators_include_surface_and_standalone_volume_paths() -> None:
    keys = set(supported_3d_mesh_generators())
    assert {"structured_hex8_box", "structured_tet4_box", "voxel_hex8_from_stl", "gmsh_tet4_from_stl", "conformal_tet4_from_stl_regions"} <= keys
    all_keys = set(meshing.supported_mesh_generators())
    assert {"structured_hex8_box", "structured_tet4_box"} <= all_keys
