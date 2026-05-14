from __future__ import annotations

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.mesh.mesh_document import MeshDocument
from geoai_simkit.services.geology_fem_analysis_workflow import (
    WORKFLOW_CONTRACT,
    check_imported_geology_fem_state,
    run_complete_imported_geology_fem_analysis,
)


def _two_layer_tet_project():
    project = GeoProjectDocument.create_empty(name="imported-geology-fem")
    mesh = MeshDocument(
        nodes=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (0.0, 1.0, 1.0),
            (0.0, 0.0, 2.0),
        ],
        cells=[(0, 1, 2, 3), (4, 5, 6, 7)],
        cell_types=["tet4", "tet4"],
        cell_tags={
            "geology_layer_id": ["101", "202"],
            "display_group": ["101", "202"],
            "block_id": ["imported_geology_model", "imported_geology_model"],
        },
        metadata={"source": "unit_test_imported_vtu_like_mesh"},
    )
    project.mesh_model.attach_mesh(mesh)
    return project


def test_imported_geology_check_creates_layer_material_and_block_mapping():
    project = _two_layer_tet_project()

    report = check_imported_geology_fem_state(project)
    payload = report.to_dict()

    assert payload["contract"] == WORKFLOW_CONTRACT
    assert report.ok is True
    assert project.metadata["imported_geology_fem_prepared"] is True
    assert set(project.metadata["imported_geology_layer_to_volume"].values()) == {
        "geology_layer_layer_101",
        "geology_layer_layer_202",
    }
    mesh = project.mesh_model.mesh_document
    assert mesh is not None
    assert set(mesh.cell_tags["block_id"]) == {"geology_layer_layer_101", "geology_layer_layer_202"}
    assert set(mesh.cell_tags["material_id"]) == {"soil_layer_101", "soil_layer_202"}


def test_complete_imported_geology_fem_analysis_solves_and_exposes_result_views():
    events = []
    project = _two_layer_tet_project()

    report = run_complete_imported_geology_fem_analysis(project, element_size=1.0, surcharge_qz=0.0, progress_callback=events.append)
    payload = report.to_dict()

    assert payload["ok"] is True
    assert payload["stage"] == "complete"
    assert {row["key"] for row in payload["steps"]} >= {"prepare", "check", "mesh", "stress", "compile", "solve", "results"}
    steady = project.metadata["last_imported_geology_steady_solve"]["metadata"]["steady_state"]
    assert steady["accepted"] is True
    assert project.result_store.phase_results
    available = payload["metadata"]["results"]["available_views"]
    assert {"displacement", "uz", "cell_stress_zz", "cell_von_mises", "cell_equivalent_strain"} <= set(available)
    assert events and events[-1]["percent"] == 100
