from __future__ import annotations

from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def test_phase_workbench_payload_exposes_imported_geology_fem_panel():
    payload = build_phase_workbench_qt_payload()

    fem = payload["imported_geology_fem_analysis"]
    assert fem["contract"] == "geoai_simkit_imported_geology_fem_analysis_workflow_v1"
    assert fem["gui_panel"] == "FEM分析流程"
    assert payload["gui_cleanup"]["right_dock_tabs"] == ["属性", "语义/材料/阶段", "导入拼接", "FEM分析流程", "结构建模", "材料库"]
    assert fem["progress_events"] is True
    assert "cell_von_mises" in fem["result_views"]


def test_gui_action_audit_includes_fem_workflow_actions():
    payload = build_phase_workbench_qt_payload()
    critical = set(payload["gui_action_audit"]["critical_actions"])

    assert {
        "fem_check_imported_geology",
        "fem_generate_or_repair_mesh",
        "fem_solve_to_steady_state",
        "fem_refresh_result_view",
        "fem_run_complete_analysis",
    } <= critical
