from __future__ import annotations

from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.app.viewport.visualization_diagnostics import build_gui_visualization_diagnostic
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def test_loaded_demo_has_visible_gui_primitives() -> None:
    project = load_demo_project("foundation_pit_3d_beta")
    diagnostic = build_gui_visualization_diagnostic(project).to_dict()
    assert diagnostic["ok"] is True
    assert diagnostic["primitive_count"] > 0
    assert diagnostic["visible_primitive_count"] > 0
    assert diagnostic["block_count"] > 0
    assert diagnostic["bounds"] is not None


def test_phase_workbench_payload_exposes_demo_center_and_visualization_contract() -> None:
    payload = build_phase_workbench_qt_payload("geology")
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert payload["demo_center"]["one_click_load"] is True
    assert "run_complete_calculation" in payload["demo_center"]["actions"]
    assert len(payload["phase_tabs"]) == 6
