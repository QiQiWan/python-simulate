from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    from geoai_simkit._version import __version__
    from geoai_simkit.app.launcher_entry import _launcher_info

    phase_source = _text("src/geoai_simkit/app/shell/phase_workbench_qt.py")
    launch_source = _text("src/geoai_simkit/app/launch.py")
    cli_source = _text("src/geoai_simkit/cli.py")
    workbench_window = _text("src/geoai_simkit/app/workbench_window.py")
    modern_workbench = _text("src/geoai_simkit/app/modern_qt_workbench.py")
    main_window = _text("src/geoai_simkit/app/main_window.py")
    unified = _text("src/geoai_simkit/app/shell/unified_workbench_window.py")
    info = _launcher_info(ROOT, "start_gui.py")

    checks = {
        "version": __version__,
        "launcher_contract_v9": info.get("contract") == "geoai_simkit_gui_launcher_info_v9",
        "canonical_workbench_phase_qt": info.get("canonical_workbench_module") == "geoai_simkit.app.shell.phase_workbench_qt",
        "legacy_workbench_window_skipped": bool(info.get("legacy_workbench_window_skipped")),
        "launch_only_imports_phase_workbench": "launch_phase_workbench_qt" in launch_source and "launch_unified_workbench" not in launch_source and "launch_nextgen_workbench" not in launch_source,
        "cli_gui_uses_launcher_entry": "from geoai_simkit.app.launcher_entry import main as launcher_main" in cli_source,
        "legacy_workbench_window_redirected": "NextGenWorkbenchWindow" not in workbench_window and "launch_phase_workbench_qt" in workbench_window,
        "legacy_modern_qt_redirected": "QGraphicsView" not in modern_workbench and "launch_phase_workbench_qt" in modern_workbench,
        "legacy_main_window_redirected": "main_window_impl" not in main_window and "Legacy MainWindow is disabled" in main_window,
        "unified_launcher_redirected": "launch_nextgen_workbench" not in unified and "launch_phase_workbench_qt" in unified,
        "action_state_contract_present": "GUI_ACTION_STATE_CONTRACT" in phase_source and "GuiActionStateRegistry" in phase_source,
        "generic_import_buttons_dispatch": "import_geology_model" in phase_source and "import_structure_model" in phase_source and "prefer_existing_path=False" in phase_source,
        "modal_qfiledialog_exec_removed_from_phase_workbench": "QFileDialog.exec(" not in phase_source and "dialog.exec(" not in phase_source,
        "active_dialogs_retained": "self._active_file_dialogs[action_id] = dialog" in phase_source,
        "audit_table_has_dialog_column": "Dialog" in phase_source and "dialog_policy" in phase_source,
        "msh_vtu_geology_import_supported": "msh_geology" in phase_source and "vtu_geology" in phase_source and "*.msh *.vtu" in phase_source,
        "meshio_array_truth_value_repair": "raw_points = getattr(mesh, \"points\", None)" in _text("src/geoai_simkit/geology/importers/meshio_importer.py") and "getattr(mesh, \"points\", []) or []" not in _text("src/geoai_simkit/geology/importers/meshio_importer.py"),
        "meshio_ascii_fallback_supported": "_parse_ascii_vtu" in _text("src/geoai_simkit/geology/importers/meshio_importer.py") and "_parse_gmsh_v2" in _text("src/geoai_simkit/geology/importers/meshio_importer.py"),
        "startup_scene_empty_by_default": "GeoProjectDocument.create_empty" in phase_source and "startup_empty_scene" in phase_source,
        "old_format_specific_buttons_removed": 'QPushButton("导入地质 STL")' not in phase_source and 'QPushButton("导入结构 STL")' not in phase_source and 'QPushButton("导入地质 IFC/STEP")' not in phase_source,
        "top_toolbar_slimmed": "CAD 建模控制" not in phase_source and "创建点" not in phase_source.split("def _build_structure_modeling_panel", 1)[0],
        "runtime_button_smoke_present": "def _run_gui_button_smoke_from_gui" in phase_source and "geoai_simkit_runtime_button_smoke_v1" in phase_source and "run_gui_button_smoke" in phase_source,
        "gui_action_widgets_tracked": "self._gui_action_widgets" in phase_source and 'button.setProperty("geoai_action_id"' in phase_source,
        "production_actions_registered": all(action in phase_source for action in ["import_geology_model", "import_geology_auto", "import_structure_model", "import_structure_auto", "register_structure_box", "run_import_driven_assembly", "run_native_import_assembly", "assign_material_to_selection", "refresh_workbench_state", "run_gui_button_smoke"]),
        "historical_ribbon_startup_safe": "self.ribbon.clear()" not in phase_source and "def _rebuild_ribbon" in phase_source and "self.ribbon = None" in phase_source,
        "mesh_visualization_overlay_supported": "render_project_mesh_overlay" in _text("src/geoai_simkit/app/viewport/pyvista_adapter.py") and "geoai-imported-geology-surface" in _text("src/geoai_simkit/app/viewport/pyvista_adapter.py") and "categories=True" in _text("src/geoai_simkit/app/viewport/pyvista_adapter.py"),
        "fem_mesh_quality_tools_present": "check_fem_mesh_quality" in phase_source and "optimize_fem_mesh" in phase_source and "refresh_mesh_visualization" in phase_source and "identify_geology_layers" in phase_source and "reduce_mesh_weight" in phase_source and "diagnose_nonmanifold_mesh" in phase_source,
        "fem_mesh_quality_service_present": "FEM_MESH_QUALITY_CONTRACT" in _text("src/geoai_simkit/mesh/fem_quality.py") and "optimize_mesh_for_fem" in _text("src/geoai_simkit/mesh/fem_quality.py") and "diagnose_nonmanifold_mesh" in _text("src/geoai_simkit/mesh/fem_quality.py") and "reduce_mesh_weight" in _text("src/geoai_simkit/mesh/fem_quality.py"),
        "paraview_soil_id_scalar_preserved": "preferred_geology_scalar" in _text("src/geoai_simkit/geology/importers/meshio_importer.py") and "soil_id" in _text("src/geoai_simkit/geology/importers/meshio_importer.py"),
    }
    checks["ok"] = all(v for k, v in checks.items() if k not in {"version"})
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if checks["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
