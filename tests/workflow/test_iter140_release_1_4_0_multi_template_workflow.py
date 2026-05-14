from __future__ import annotations

from pathlib import Path

from geoai_simkit import __version__
from geoai_simkit.app.panels.release_140_showcase import build_release_1_4_0_showcase_payload, create_release_1_4_0_showcase_project
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.examples.release_1_4_0_workflow import run_release_1_4_0_template_workflow, run_release_1_4_0_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.demo_project_runner import build_demo_catalog, load_demo_project, run_demo_complete_calculation
from geoai_simkit.services.demo_templates import build_engineering_template_catalog
from geoai_simkit.services.release_acceptance_140 import audit_release_1_4_0


def test_release_1_4_0_version_and_catalog() -> None:
    assert __version__ in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    catalog = build_engineering_template_catalog()
    assert catalog["contract"] == "geoai_simkit_engineering_template_catalog_v1"
    assert catalog["template_count"] == 3
    assert {row["demo_id"] for row in catalog["templates"]} == {
        "foundation_pit_3d_beta",
        "slope_stability_beta",
        "pile_soil_interaction_beta",
    }
    assert "run_all_templates" in catalog["actions"]


def test_demo_runner_loads_all_1_4_templates() -> None:
    catalog = build_demo_catalog()
    assert catalog["release"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert catalog["template_count"] == 3
    for demo_id in ("foundation_pit_3d_beta", "slope_stability_beta", "pile_soil_interaction_beta"):
        project = load_demo_project(demo_id)
        assert project.metadata["release"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
        assert project.metadata["release_1_4_0_demo"]["demo_id"] == demo_id
        assert project.mesh_model.mesh_document is not None
        assert project.result_store.phase_results


def test_phase_workbench_qt_payload_exposes_1_4_multi_template_center() -> None:
    payload = build_phase_workbench_qt_payload("solve")
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert payload["version"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert payload["demo_center"]["contract"] == "phase_workbench_demo_center_v2"
    assert payload["demo_center"]["template_count"] == 3
    assert "run_all_templates" in payload["demo_center"]["actions"]


def test_single_template_complete_calculation_and_bundle(tmp_path: Path) -> None:
    result = run_release_1_4_0_template_workflow("pile_soil_interaction_beta", output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_4_0_template_workflow_v1"
    assert result["ok"] is True
    assert result["project"].metadata["release_1_4_0_demo"]["template_family"] == "pile_soil_interaction"
    assert result["pipeline"]["ok"] is True
    artifacts = result["artifacts"]
    for key in ("project_path", "acceptance_path", "demo_run_path", "vtk_path", "report_markdown_path", "report_json_path", "tutorial_path"):
        assert Path(artifacts[key]).exists(), key
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.metadata["release"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert reloaded.metadata["active_demo_id"] == "pile_soil_interaction_beta"


def test_release_1_4_0_runs_all_templates(tmp_path: Path) -> None:
    result = run_release_1_4_0_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_release_1_4_0_workflow_v1"
    assert result["ok"] is True
    acceptance = result["acceptance"]
    assert acceptance["status"] == "accepted_1_4_0_beta2"
    assert acceptance["completed_template_count"] == 3
    assert acceptance["blocker_count"] == 0
    assert set(result["template_results"]) == {"foundation_pit_3d_beta", "slope_stability_beta", "pile_soil_interaction_beta"}
    artifacts = result["artifacts"]
    for key in ("catalog_path", "summary_path", "acceptance_path", "gui_payload_path", "tutorial_path"):
        assert Path(artifacts[key]).exists(), key


def test_release_1_4_0_acceptance_blocks_missing_template(tmp_path: Path) -> None:
    result = run_release_1_4_0_workflow(output_dir=tmp_path)
    accepted = audit_release_1_4_0(catalog=result["catalog"], template_results=result["template_results"], aggregate_artifacts=result["artifacts"], gui_payload=result["gui_payload"])
    assert accepted.accepted
    missing = dict(result["template_results"])
    missing.pop("slope_stability_beta")
    blocked = audit_release_1_4_0(catalog=result["catalog"], template_results=missing, aggregate_artifacts=result["artifacts"], gui_payload=result["gui_payload"])
    assert not blocked.accepted
    assert any(f.code == "template.slope_stability_beta.missing" for f in blocked.findings)


def test_release_1_4_0_showcase_payload() -> None:
    project = create_release_1_4_0_showcase_project("slope_stability_beta")
    payload = build_release_1_4_0_showcase_payload(project, active_demo_id="slope_stability_beta")
    assert payload["contract"] == "release_1_4_0_showcase_panel_v1"
    assert payload["release"] in {"1.4.2a-cad-facade", "1.4.5-native-geometry-certification", "1.4.6-cad-workbench-stabilization", "1.4.8-cad-fem-preprocessor", "1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    assert payload["demo_center"]["template_count"] == 3
    assert payload["project_demo"]["demo_id"] == "slope_stability_beta"
