from __future__ import annotations

from pathlib import Path

from geoai_simkit import __version__
from geoai_simkit.app.panels.release_130_showcase import build_release_1_3_0_showcase_payload
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.examples.release_1_3_0_workflow import build_release_1_3_0_project, run_release_1_3_0_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.demo_project_runner import build_demo_catalog, load_demo_project, run_demo_complete_calculation
from geoai_simkit.services.release_acceptance_130 import audit_release_1_3_0


def test_release_1_3_0_build_is_one_click_loadable() -> None:
    assert __version__ in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    project, build = build_release_1_3_0_project()
    assert project.metadata["release"] == "1.3.0-beta"
    assert build["contract"] == "geoai_simkit_release_1_3_0_build_v1"
    assert build["demo"]["demo_id"] == "foundation_pit_3d_beta"
    assert build["demo"]["one_click_load"] is True
    assert build["demo"]["complete_calculation"] is True
    assert build["gui_payload"]["demo_center"]["actions"] == ["load_demo_project", "run_complete_calculation", "export_demo_bundle"]


def test_demo_catalog_and_phase_workbench_payload_expose_demo_center() -> None:
    catalog = build_demo_catalog()
    assert catalog["contract"] == "geoai_simkit_demo_catalog_v1"
    assert catalog["default_demo_id"] == "foundation_pit_3d_beta"
    assert catalog["demos"][0]["complete_calculation"] is True
    payload = build_phase_workbench_qt_payload("solve")
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert payload["version"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert payload["demo_center"]["one_click_load"] is True
    assert payload["demo_center"]["complete_calculation"] is True
    assert "run_complete_calculation" in payload["demo_center"]["actions"]


def test_one_click_load_returns_beta_demo_project() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    assert project.metadata["release"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert project.metadata["release_1_4_0_demo"]["demo_id"] == "foundation_pit_3d_beta"
    assert project.metadata["loaded_from_demo_center"] is True
    assert project.mesh_model.mesh_document is not None
    assert project.result_store.phase_results


def test_release_1_3_0_complete_calculation_workflow_and_bundle(tmp_path: Path) -> None:
    result = run_release_1_3_0_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_3_0_workflow_v1"
    assert result["ok"] is True
    assert result["acceptance"]["status"] == "accepted_1_3_0_beta"
    assert result["acceptance"]["blocker_count"] == 0
    assert result["pipeline"]["ok"] is True
    assert [step["key"] for step in result["pipeline"]["steps"]] == ["load_demo", "geology_structure", "mesh", "compile", "solve", "hydro_contact", "results_export"]
    artifacts = result["artifacts"]
    for key in (
        "project_path",
        "validation_path",
        "compiler_path",
        "global_newton_path",
        "acceptance_path",
        "demo_run_path",
        "gui_payload_path",
        "result_viewer_path",
        "result_export_path",
        "vtk_path",
        "report_markdown_path",
        "report_json_path",
        "tutorial_path",
    ):
        assert Path(artifacts[key]).exists(), key
    tutorial = Path(artifacts["tutorial_path"]).read_text(encoding="utf-8")
    assert "GeoAI SimKit 1.3.0 Beta Demo Tutorial" in tutorial
    assert "运行完整计算流程" in tutorial
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.metadata["release"] == "1.3.0-beta"
    assert reloaded.metadata["release_1_3_0_pipeline"]["ok"] is True


def test_demo_runner_runs_complete_calculation(tmp_path: Path) -> None:
    result = run_demo_complete_calculation(output_dir=tmp_path)
    payload = result.to_dict(include_project=False)
    assert payload["contract"] == "geoai_simkit_demo_run_result_v1"
    assert payload["ok"] is True
    assert Path(payload["artifacts"]["project_path"]).exists()
    assert payload["workflow"]["acceptance"]["accepted"] is True


def test_release_1_3_0_acceptance_blocks_missing_pipeline(tmp_path: Path) -> None:
    result = run_release_1_3_0_workflow(output_dir=tmp_path)
    project = result["project"]
    accepted = audit_release_1_3_0(project, pipeline=result["pipeline"], artifacts=result["artifacts"], gui_payload=result["gui_payload"])
    assert accepted.accepted
    blocked = audit_release_1_3_0(project, pipeline={}, artifacts=result["artifacts"], gui_payload=result["gui_payload"])
    assert not blocked.accepted
    assert any(finding.code == "pipeline.missing" for finding in blocked.findings)


def test_release_1_3_0_showcase_payload_is_demo_aware(tmp_path: Path) -> None:
    result = run_release_1_3_0_workflow(output_dir=tmp_path)
    payload = build_release_1_3_0_showcase_payload(result["project"])
    assert payload["contract"] == "release_1_3_0_showcase_panel_v1"
    assert payload["release"] == "1.3.0-beta"
    assert payload["demo_center"]["one_click_load"] is True
    assert "load_demo_project" in payload["actions"]
    assert "run_complete_calculation" in payload["actions"]
