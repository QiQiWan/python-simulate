from __future__ import annotations

import json

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.mesh.mesh_document import MeshDocument
from geoai_simkit.modules import meshing
from geoai_simkit.services import run_project_workflow


def _attach(project: GeoProjectDocument, mesh: MeshDocument) -> GeoProjectDocument:
    project.mesh_model.attach_mesh(mesh)
    return project


def _surface_project() -> GeoProjectDocument:
    project = GeoProjectDocument.create_empty(name="occ-fragment")
    nodes = [
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0),
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


def test_gmsh_occ_fragment_report_falls_back_cleanly_without_optional_dependencies(tmp_path) -> None:
    project = _surface_project()
    report = meshing.gmsh_occ_fragment_tet4_mesh(
        project,
        layers=[{"layer_id": "layer_a", "z_min": 0.0, "z_max": 1.0, "material_id": "soil"}],
        allow_fallback=True,
        debug=True,
        debug_dir=str(tmp_path),
    )
    assert report["metadata"]["contract"] == "gmsh_occ_fragment_meshing_report_v1"
    assert report["ok"] is True
    assert report["generated_cell_count"] > 0
    assert project.mesh_model.mesh_document.metadata["mesh_kind"] in {"soil_layered_volume_from_stl", "gmsh_occ_fragment_tet4_from_stl"}

    log_path = tmp_path / "geometry_kernel.jsonl"
    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["operation"] == "gmsh_occ_fragment_tet4"
    assert rows[-1]["output_state"]["metadata"]["contract"] == "gmsh_occ_fragment_meshing_report_v1"


def test_gmsh_occ_fragment_generator_and_workflow_artifacts() -> None:
    project = _surface_project()
    assert "gmsh_occ_fragment_tet4_from_stl" in meshing.supported_mesh_generators()
    workflow = run_project_workflow(
        project,
        mesh_kind="gmsh_occ_fragment_tet4_from_stl",
        compile_stages=False,
        solve=False,
        summarize=False,
        metadata={
            "mesh_options": {
                "layers": [{"layer_id": "gmsh_layer", "z_min": 0.0, "z_max": 1.0, "material_id": "soil"}],
                "allow_fallback": True,
            }
        },
    )
    assert workflow.ok
    assert workflow.artifact_ref("mesh3d") is not None
    assert workflow.artifact_ref("geometry_kernel") is not None
    assert project.mesh_model.mesh_document.cell_count > 0


def test_local_remesh_replaces_bad_hex_with_tet_cells() -> None:
    project = GeoProjectDocument.create_empty(name="local-remesh")
    # Very skewed but positive-volume hex cell; aspect gate will mark it bad.
    mesh = MeshDocument(
        nodes=[
            (0, 0, 0), (100, 0, 0), (100, 1, 0), (0, 1, 0),
            (0, 0, 1), (100, 0, 1), (100, 1, 1), (0, 1, 1),
        ],
        cells=[(0, 1, 2, 3, 4, 5, 6, 7)],
        cell_types=["hex8"],
        cell_tags={"block_id": ["bad_hex"], "region_name": ["bad_hex"], "material_id": ["soil"], "role": ["solid_volume"]},
        metadata={"mesh_role": "solid_volume", "solid_solver_ready": True},
    )
    _attach(project, mesh)
    report = meshing.local_remesh_project_volume_mesh_quality(project, max_aspect_ratio=10.0, attach=True)
    assert report["metadata"]["contract"] == "local_remesh_report_v1"
    assert report["remeshed_bad_cell_count"] == 1
    assert report["removed_bad_cell_count"] == 0
    assert set(project.mesh_model.mesh_document.cell_types) == {"tet4"}
    assert project.mesh_model.mesh_document.cell_count == 5
