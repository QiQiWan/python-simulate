from __future__ import annotations

from pathlib import Path

from geoai_simkit.app.panels.alpha_showcase import build_alpha_showcase_payload
from geoai_simkit.examples.alpha_0_9_workflow import build_alpha_foundation_pit_project, run_alpha_foundation_pit_workflow
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.services.model_validation import validate_geoproject_model
from geoai_simkit.services.phase_solver_compiler import compile_phase_solver_inputs
from geoai_simkit.services.system_audit import audit_geoproject_alpha


def test_alpha_0_9_builds_plaxis_like_staged_foundation_pit() -> None:
    project = build_alpha_foundation_pit_project()
    assert project.project_settings.metadata["alpha_release"] == "0.9.0"
    assert project.phase_ids() == ["initial", "excavation_1", "support_1", "excavation_2", "support_2"]
    assert "excavation_step_1" not in project.phase_manager.phase_state_snapshots["excavation_1"].active_volume_ids
    assert "excavation_step_2" not in project.phase_manager.phase_state_snapshots["excavation_2"].active_volume_ids
    assert "strut_strut_level_1" in project.phase_manager.phase_state_snapshots["support_1"].active_structure_ids
    assert "strut_strut_level_2" in project.phase_manager.phase_state_snapshots["support_2"].active_structure_ids


def test_alpha_0_9_validation_and_phase_compiler_contracts() -> None:
    project = build_alpha_foundation_pit_project()
    validation = validate_geoproject_model(project, require_mesh=True)
    assert validation.ok
    assert validation.readiness["geometry_ready"]
    assert validation.readiness["semantic_ready"]
    assert validation.readiness["mesh_ready"]

    compiler = compile_phase_solver_inputs(project)
    assert compiler.ok
    assert compiler.compiled_phase_count == len(project.phase_ids())
    assert all(row["has_mesh_block"] for row in compiler.phase_summaries)
    assert all(row["has_material_block"] for row in compiler.phase_summaries)


def test_alpha_0_9_end_to_end_bundle_and_audit(tmp_path: Path) -> None:
    result = run_alpha_foundation_pit_workflow(output_dir=tmp_path)
    assert result["contract"] == "geoai_simkit_alpha_0_9_workflow_v1"
    assert result["ok"] is True
    assert result["solver_summary"]["result_phase_count"] == 5
    assert result["viewer"]["available"] is True
    assert result["audit"]["blocker_count"] == 0
    artifacts = result["artifacts"]
    for key in ("project_path", "validation_path", "compiler_path", "solver_summary_path", "result_summary_path", "audit_path", "vtk_path"):
        assert Path(artifacts[key]).exists(), key
    reloaded = GeoProjectDocument.load_json(artifacts["project_path"])
    assert reloaded.phase_ids() == ["initial", "excavation_1", "support_1", "excavation_2", "support_2"]
    assert len(reloaded.result_store.phase_results) == 5


def test_alpha_0_9_gui_payload_is_stage_aware() -> None:
    project = build_alpha_foundation_pit_project()
    payload = build_alpha_showcase_payload(project)
    assert payload["contract"] == "alpha_0_9_showcase_panel_v1"
    assert len(payload["phase_rows"]) == 5
    assert payload["readiness"]["mesh_ready"] is True
    assert "run_alpha_foundation_pit_workflow" in payload["actions"]


def test_alpha_0_9_audit_reports_preview_mesh_risk_after_results() -> None:
    result = run_alpha_foundation_pit_workflow()
    project = result["project"]
    audit = audit_geoproject_alpha(project)
    assert audit.blocker_count == 0
    assert audit.status in {"alpha_ready", "alpha_ready_with_risks"}
    assert any(finding.area == "mesh" for finding in audit.findings)
