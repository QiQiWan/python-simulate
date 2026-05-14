from __future__ import annotations

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.app.viewport.opengl_context_guard import (
    OPENGL_CONTEXT_GUARD_CONTRACT,
    OpenGLContextGuardState,
    build_default_qt_vtk_opengl_policy,
    widget_exposure_state,
)
from geoai_simkit.core.gui_workflow_module_spec import build_gui_workflow_module_payload


class _HiddenWidget:
    def isVisible(self) -> bool:
        return False

    def isHidden(self) -> bool:
        return True

    def isEnabled(self) -> bool:
        return True


def test_iter152_module_matrix_covers_cad_to_solver_workflow() -> None:
    assert __version__ == "1.5.4-viewport-workplane-hover-creation"
    payload = build_gui_workflow_module_payload()
    assert payload["ok"] is True
    assert payload["module_count"] >= 10
    keys = set(payload["lifecycle_order"])
    assert {
        "project_data_intake",
        "structure_modeling",
        "native_cad_topology",
        "material_library",
        "stage_and_construction_sequence",
        "topology_preprocess",
        "meshing_workbench",
        "solver_setup_and_run",
        "results_and_reporting",
        "benchmark_readiness",
        "runtime_diagnostics",
    }.issubset(keys)
    meshing = next(row for row in payload["modules"] if row["key"] == "meshing_workbench")
    meshing_elements = {row["key"] for row in meshing["required_elements"]}
    assert {"mesher_backend_selector", "global_mesh_size", "mesh_quality_table", "mesh_entity_map_view"}.issubset(meshing_elements)
    solver = next(row for row in payload["modules"] if row["key"] == "solver_setup_and_run")
    solver_actions = {action for element in solver["required_elements"] for action in element["actions"]}
    assert {"run_solver", "cancel_solver", "refresh_solve_precheck"}.issubset(solver_actions)


def test_iter152_qt_payload_exposes_opengl_guard_and_cleaned_gui_contract() -> None:
    payload = build_phase_workbench_qt_payload()
    guard = payload["opengl_context_guard"]
    assert guard["contract"] == OPENGL_CONTEXT_GUARD_CONTRACT
    assert "set AA_ShareOpenGLContexts before QApplication creation" in guard["fixes"]
    assert payload["gui_cleanup"]["centralized_logs"] is True
    assert payload["gui_cleanup"]["right_side_explanations_are_floating"] is True
    assert "模块界面" in payload["gui_cleanup"]["bottom_tabs"]
    runtime = next(row for row in payload["workflow_module_specs"]["modules"] if row["key"] == "runtime_diagnostics")
    element_keys = {row["key"] for row in runtime["required_elements"]}
    assert {"unified_log_tab", "viewport_diagnostic_tab", "opengl_guard_status", "dependency_tab"}.issubset(element_keys)


def test_iter152_opengl_guard_state_and_exposure_skip_hidden_widgets() -> None:
    policy = build_default_qt_vtk_opengl_policy()
    assert policy.to_dict()["contract"] == OPENGL_CONTEXT_GUARD_CONTRACT
    assert "GEOAI_SIMKIT_DISABLE_PYVISTA=1" in " ".join(policy.to_dict()["fallbacks"])
    state = OpenGLContextGuardState()
    state.render_attempts += 1
    state.skipped_renders += 1
    state.last_reason = "window_not_exposed"
    assert state.to_dict()["skipped_renders"] == 1
    exposure = widget_exposure_state(_HiddenWidget())
    assert exposure["renderable"] is False
    assert exposure["reason"] in {"widget_visible_False", "widget_hidden_True"}
