from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import _launcher_info
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.geology.importers.contracts import GeologyImportRequest
from geoai_simkit.geology.importers.registry import get_default_geology_importer_registry


def test_version_launcher_and_old_gui_entrypoints_are_disabled() -> None:
    assert __version__ == "1.6.6-runtime-action-smoke"
    info = _launcher_info(Path.cwd(), "start_gui.py")
    assert info["contract"] == "geoai_simkit_gui_launcher_info_v6"
    assert info["canonical_workbench_module"] == "geoai_simkit.app.shell.phase_workbench_qt"
    assert info["legacy_workbench_window_skipped"] is True
    assert info["legacy_gui_modules_disabled"]
    assert info["file_dialog_policy"] == "explicit_path_first_plus_dialog_action_dispatcher"


def test_generic_import_buttons_replace_format_specific_stl_buttons() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert 'QPushButton("导入地质/钻孔")' in source
    assert 'QPushButton("导入结构/围护")' in source
    assert 'import_geology_model' in source
    assert 'import_structure_model' in source
    assert "*.msh *.vtu" in source
    assert 'QPushButton("导入地质 STL")' not in source
    assert 'QPushButton("导入结构 STL")' not in source
    assert 'QPushButton("导入地质 IFC/STEP")' not in source


def test_msh_vtu_source_types_are_registered() -> None:
    registry = get_default_geology_importer_registry()
    supported = set(registry.supported_source_types())
    assert {"msh_geology", "vtu_geology", "meshio_geology"}.issubset(supported)
    assert GeologyImportRequest("geology.msh").normalized_source_type == "msh_geology"
    assert GeologyImportRequest("geology.vtu").normalized_source_type == "vtu_geology"


def test_payload_exposes_import_driven_mesh_sources_and_slim_toolbar() -> None:
    payload = build_phase_workbench_qt_payload()
    native = payload["geometry_interaction"]["native_import_assembly"]
    assert {"msh", "vtu"}.issubset(set(native["supported_sources"]))
    assert native["direct_import_buttons"] == ["import_geology_model", "import_structure_model"]
    cleanup = payload["gui_cleanup"]
    assert "导入拼接" in cleanup["right_dock_tabs"]
    assert "交互自检" in cleanup["bottom_tabs"]


def test_action_flow_checker_reports_unified_state_ok() -> None:
    proc = subprocess.run([sys.executable, "tools/check_gui_action_flow.py"], check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["version"] == __version__
    assert payload["generic_import_buttons_dispatch"] is True
    assert payload["msh_vtu_geology_import_supported"] is True
    assert payload["top_toolbar_slimmed"] is True
