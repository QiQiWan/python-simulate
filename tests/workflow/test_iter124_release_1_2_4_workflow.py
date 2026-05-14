from __future__ import annotations

from pathlib import Path

from geoai_simkit import __version__
from geoai_simkit.app.panels.release_124_showcase import build_release_1_2_4_showcase_payload
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.examples.release_1_2_4_workflow import build_release_1_2_4_project, run_release_1_2_4_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.gui_interaction_recording import record_phase_workbench_interaction_contract
from geoai_simkit.services.release_acceptance_124 import audit_release_1_2_4


def test_release_1_2_4_build_adds_global_newton_exchange_and_gui_fix(tmp_path: Path) -> None:
    assert __version__ in {"1.3.0-beta", "1.4.2a-cad-facade", "1.4.2c-native-roundtrip", "1.4.2d-cad-shape-store", "1.4.3-step-ifc-shape-binding", "1.4.4-topology-binding", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    project, build = build_release_1_2_4_project(exchange_dir=tmp_path)
    assert project.metadata["release"] == "1.2.4-basic"
    assert build["contract"] == "geoai_simkit_release_1_2_4_build_v1"
    assert build["global_newton"]["contract"] == "geoai_simkit_global_mohr_coulomb_newton_solver_v1"
    assert build["global_newton"]["accepted"] is True
    assert build["gmsh_exchange"]["contract"] == "geoai_simkit_gmsh_occ_native_exchange_v1"
    assert build["gmsh_exchange"]["ok"] is True
    assert Path(build["gmsh_exchange"]["manifest_path"]).exists()
    assert build["consolidation"]["ok"] is True
    assert build["interface_iteration"]["ok"] is True
    assert build["gui_recording"]["old_gui_blocked"] is True


def test_phase_qt_payload_shows_six_phase_launcher_not_legacy() -> None:
    payload = build_phase_workbench_qt_payload()
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert len(payload["phase_tabs"]) == 6
    assert payload["launcher_fix"]["default_when_pyvista_missing"] == "launch_phase_workbench_qt"
    assert payload["launcher_fix"]["legacy_flat_editor_default"] is False
    labels = [row["label"] for row in payload["phase_tabs"]]
    assert labels == ["地质", "结构", "网格", "阶段配置", "求解", "结果查看"]


def test_gui_interaction_recording_contract() -> None:
    report = record_phase_workbench_interaction_contract()
    payload = report.to_dict()
    assert payload["contract"] == "geoai_simkit_gui_interaction_recording_v1"
    assert payload["ok"] is True
    assert payload["phase_count"] == 6
    assert payload["phase_sequence"] == ["geology", "structures", "mesh", "staging", "solve", "results"]
    assert payload["old_gui_blocked"] is True


def test_release_1_2_4_end_to_end_acceptance_and_bundle(tmp_path: Path) -> None:
    result = run_release_1_2_4_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_2_4_workflow_v1"
    assert result["ok"] is True
    assert result["acceptance"]["status"] == "accepted_1_2_4_basic"
    assert result["acceptance"]["blocker_count"] == 0
    assert result["newton_summary"]["accepted"] is True
    assert result["consolidation"]["ok"] is True
    assert result["interface_iteration"]["ok"] is True
    artifacts = result["artifacts"]
    for key in (
        "project_path",
        "validation_path",
        "gui_recording_path",
        "compiler_path",
        "newton_summary_path",
        "acceptance_path",
        "gmsh_exchange_path",
        "consolidation_path",
        "interface_iteration_path",
        "result_viewer_path",
        "result_export_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
        "tutorial_path",
    ):
        assert Path(artifacts[key]).exists(), key
    tutorial = Path(artifacts["tutorial_path"]).read_text(encoding="utf-8")
    assert "GeoAI SimKit 1.2.4 Basic Tutorial" in tutorial
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.metadata["release"] == "1.2.4-basic"
    assert "last_global_mohr_coulomb_newton_solve" in reloaded.solver_model.metadata
    assert "consolidation_coupling_state" in reloaded.solver_model.metadata
    assert "interface_contact_iteration" in reloaded.solver_model.metadata


def test_release_1_2_4_acceptance_blocks_missing_gui_recording_or_newton() -> None:
    result = run_release_1_2_4_workflow()
    project = result["project"]
    accepted = audit_release_1_2_4(project, newton_summary=result["newton_summary"])
    assert accepted.accepted
    project.solver_model.metadata.pop("last_global_mohr_coulomb_newton_solve", None)
    blocked = audit_release_1_2_4(project)
    assert not blocked.accepted
    assert any(finding.code == "newton.missing" for finding in blocked.findings)


def test_release_1_2_4_showcase_payload_is_acceptance_aware() -> None:
    result = run_release_1_2_4_workflow()
    payload = build_release_1_2_4_showcase_payload(result["project"])
    assert payload["contract"] == "release_1_2_4_showcase_panel_v1"
    assert payload["release"] == "1.2.4-basic"
    assert payload["acceptance"]["accepted"] is True
    assert payload["global_newton"]["accepted"] is True
    assert "launch_phase_workbench_qt" in payload["actions"]
