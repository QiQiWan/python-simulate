from __future__ import annotations

from pathlib import Path

from geoai_simkit import __version__
from geoai_simkit.app.panels.release_113_showcase import build_release_1_1_3_showcase_payload
from geoai_simkit.examples.release_1_1_3_workflow import build_release_1_1_3_project, run_release_1_1_3_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.gui_interaction_hardening import audit_gui_interaction_hardening
from geoai_simkit.services.release_acceptance_113 import audit_release_1_1_3


def test_release_1_1_3_build_adds_mesh_contact_and_gui_layers() -> None:
    assert __version__ in {"1.1.3-basic", "1.2.4-basic", "1.3.0-beta", "1.4.2a-cad-facade", "1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    project, build = build_release_1_1_3_project()
    assert project.metadata["release"] == "1.1.3-basic"
    assert build["contract"] == "geoai_simkit_release_1_1_3_build_v1"
    assert build["mesh_route"]["contract"] == "geoai_simkit_gmsh_occ_project_mesh_v1"
    assert build["mesh_route"]["ok"] is True
    assert build["mesh_route"]["cell_count"] > 0
    assert build["contact"]["ok"] is True
    assert build["contact"]["interface_count"] > 0
    assert build["gui_interaction"]["ok"] is True
    mesh = project.mesh_model.mesh_document
    assert mesh is not None
    assert set(mesh.cell_types) == {"tet4"}
    assert mesh.metadata["requested_backend"] == "gmsh_occ_tet4"
    assert mesh.metadata["release_gate"] == "1.1.3_basic_engineering"


def test_gui_interaction_hardening_contract() -> None:
    report = audit_gui_interaction_hardening()
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_gui_interaction_hardening_v1"
    assert payload["ok"] is True
    assert payload["selection_contract_ready"] is True
    assert payload["preview_contract_ready"] is True
    assert payload["undo_redo_contract_ready"] is True
    assert payload["required_tool_count"] == 5


def test_release_1_1_3_end_to_end_acceptance_and_bundle(tmp_path: Path) -> None:
    result = run_release_1_1_3_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_1_3_workflow_v1"
    assert result["ok"] is True
    assert result["solver_summary"]["accepted"] is True
    assert result["solver_summary"]["state_count"] > 0
    assert result["hydro"]["ok"] is True
    assert result["acceptance"]["accepted"] is True
    assert result["acceptance"]["status"] == "accepted_1_1_3_basic"
    assert result["acceptance"]["blocker_count"] == 0
    artifacts = result["artifacts"]
    for key in (
        "project_path",
        "validation_path",
        "gui_interaction_path",
        "compiler_path",
        "solver_summary_path",
        "acceptance_path",
        "gmsh_occ_mesh_path",
        "hydro_path",
        "contact_path",
        "result_viewer_path",
        "result_export_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
        "tutorial_path",
    ):
        assert Path(artifacts[key]).exists(), key
    tutorial = Path(artifacts["tutorial_path"]).read_text(encoding="utf-8")
    assert "GeoAI SimKit 1.1.3 Basic Tutorial" in tutorial
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.metadata["release"] == "1.1.3-basic"
    assert reloaded.mesh_model.metadata["last_gmsh_occ_project_mesh"]["contract"] == "geoai_simkit_gmsh_occ_project_mesh_v1"
    assert "last_staged_mohr_coulomb_solve" in reloaded.solver_model.metadata
    assert "hydro_mechanical_state" in reloaded.solver_model.metadata
    assert "contact_interface_enhancement" in reloaded.solver_model.metadata


def test_release_1_1_3_acceptance_blocks_missing_hydro() -> None:
    result = run_release_1_1_3_workflow()
    project = result["project"]
    accepted = audit_release_1_1_3(project, solver_summary=result["solver_summary"])
    assert accepted.accepted
    project.solver_model.metadata.pop("hydro_mechanical_state", None)
    blocked = audit_release_1_1_3(project, solver_summary=result["solver_summary"])
    assert not blocked.accepted
    assert any(finding.code == "hydro.missing" for finding in blocked.findings)


def test_release_1_1_3_showcase_payload_is_acceptance_aware() -> None:
    result = run_release_1_1_3_workflow()
    payload = build_release_1_1_3_showcase_payload(result["project"])
    assert payload["contract"] == "release_1_1_3_showcase_panel_v1"
    assert payload["release"] == "1.1.3-basic"
    assert payload["mesh"]["cell_types"] == ["tet4"]
    assert payload["acceptance"]["accepted"] is True
    assert "run_release_1_1_3_workflow" in payload["actions"]
