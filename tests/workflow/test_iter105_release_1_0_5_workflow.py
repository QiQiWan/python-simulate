from __future__ import annotations

from pathlib import Path

from geoai_simkit import __version__
from geoai_simkit.app.panels.release_105_showcase import build_release_1_0_5_showcase_payload
from geoai_simkit.examples.release_1_0_5_workflow import build_release_1_0_5_project, run_release_1_0_5_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.gui_desktop_hardening import audit_phase_workbench_desktop_contract
from geoai_simkit.services.release_acceptance_105 import audit_release_1_0_5


def test_release_1_0_5_build_adds_hardening_layers() -> None:
    assert __version__ in {"1.0.5-basic", "1.1.3-basic", "1.2.4-basic", "1.3.0-beta", "1.4.2a-cad-facade", "1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    project, build = build_release_1_0_5_project()
    assert project.metadata["release"] == "1.0.5-basic"
    assert build["contract"] == "geoai_simkit_release_1_0_5_build_v1"
    assert build["mesh_route"]["contract"] == "geoai_simkit_gmsh_occ_mesh_route_v1"
    assert build["mesh_route"]["ok"] is True
    assert build["k0"]["ok"] is True
    assert build["k0"]["stress_state_count"] == project.mesh_model.mesh_document.cell_count
    assert build["k0"]["max_vertical_stress"] > 0.0
    assert build["mohr_coulomb"]["ok"] is True
    assert build["mohr_coulomb"]["phase_count"] == len(project.phase_ids())
    assert build["gui"]["ok"] is True
    mesh = project.mesh_model.mesh_document
    assert mesh is not None
    assert mesh.metadata["meshing_policy"] == "gmsh_occ_preferred_with_shared_hex8_fallback"
    assert mesh.metadata["selected_backend"] == "shared_node_axis_aligned_hex8"
    assert mesh.metadata["release_gate"] == "1.0.5_basic_engineering"


def test_gui_hardening_contract_is_headless_safe() -> None:
    report = audit_phase_workbench_desktop_contract()
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_gui_desktop_hardening_v1"
    assert payload["phase_count"] == 6
    assert payload["tool_count"] > 0
    assert payload["routed_tool_count"] == payload["tool_count"]
    assert payload["blocker_count"] == 0
    assert report.ok


def test_release_1_0_5_end_to_end_acceptance_and_bundle(tmp_path: Path) -> None:
    result = run_release_1_0_5_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_0_5_workflow_v1"
    assert result["ok"] is True
    assert result["solver_summary"]["accepted"] is True
    assert result["acceptance"]["accepted"] is True
    assert result["acceptance"]["status"] == "accepted_1_0_5_basic"
    assert result["acceptance"]["blocker_count"] == 0
    assert any(f["code"] == "mesh.route.fallback_used" for f in result["acceptance"]["findings"])
    artifacts = result["artifacts"]
    for key in (
        "project_path",
        "validation_path",
        "gui_hardening_path",
        "compiler_path",
        "solver_summary_path",
        "acceptance_path",
        "k0_path",
        "mohr_coulomb_path",
        "mesh_route_path",
        "result_viewer_path",
        "result_export_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
        "tutorial_path",
    ):
        assert Path(artifacts[key]).exists(), key
    report_text = Path(artifacts["report_markdown_path"]).read_text(encoding="utf-8")
    assert "1.0.5 Hardening" in report_text
    tutorial_text = Path(artifacts["tutorial_path"]).read_text(encoding="utf-8")
    assert "GeoAI SimKit 1.0.5 Basic Tutorial" in tutorial_text
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.metadata["release"] == "1.0.5-basic"
    assert reloaded.mesh_model.metadata["last_gmsh_occ_mesh_route"]["contract"] == "geoai_simkit_gmsh_occ_mesh_route_v1"
    assert "k0_initial_stress" in reloaded.solver_model.metadata
    assert "staged_mohr_coulomb_control" in reloaded.solver_model.metadata


def test_release_1_0_5_acceptance_blocks_missing_k0() -> None:
    result = run_release_1_0_5_workflow()
    project = result["project"]
    accepted = audit_release_1_0_5(project, solver_summary=result["solver_summary"])
    assert accepted.accepted
    project.solver_model.metadata.pop("k0_initial_stress", None)
    blocked = audit_release_1_0_5(project, solver_summary=result["solver_summary"])
    assert not blocked.accepted
    assert any(finding.code == "k0.missing" for finding in blocked.findings)


def test_release_1_0_5_gui_payload_is_acceptance_aware() -> None:
    result = run_release_1_0_5_workflow()
    payload = build_release_1_0_5_showcase_payload(result["project"])
    assert payload["contract"] == "release_1_0_5_showcase_panel_v1"
    assert payload["release"] == "1.0.5-basic"
    assert payload["acceptance"]["accepted"] is True
    assert "run_release_1_0_5_workflow" in payload["actions"]
