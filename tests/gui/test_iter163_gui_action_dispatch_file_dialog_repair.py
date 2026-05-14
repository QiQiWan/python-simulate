from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import _launcher_info


def test_version_and_launcher_contract_v4() -> None:
    assert __version__ == "1.6.6-runtime-action-smoke"
    info = _launcher_info(Path.cwd(), "start_gui.py")
    assert info["contract"] == "geoai_simkit_gui_launcher_info_v6"
    assert info["canonical_workbench_module"] == "geoai_simkit.app.shell.phase_workbench_qt"
    assert info["legacy_workbench_window_skipped"] is True
    assert info["file_dialog_policy"] == "explicit_path_first_plus_dialog_action_dispatcher"


def test_direct_import_buttons_use_non_modal_file_dialog_dispatch() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "def _open_import_file_dialog_async" in source
    assert "self._active_file_dialogs[action_id] = dialog" in source
    assert "WindowModality.NonModal" in source
    assert "dialog.show()" in source
    assert "dialog.exec()" not in source
    assert "import_geology_model" in source
    assert "import_structure_model" in source
    assert "*.msh *.vtu" in source
    assert "prefer_existing_path=False" in source


def test_auto_buttons_open_file_dialog_when_path_empty() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "def _import_geology_auto_clicked" in source
    assert "def _import_structure_auto_clicked" in source
    assert 'self._select_import_file_then_run(\n                "import_geology_auto"' in source
    assert 'self._select_import_file_then_run(\n                "import_structure_auto"' in source


def test_action_flow_checker_reports_dispatch_repair_ok() -> None:
    proc = subprocess.run([sys.executable, "tools/check_gui_action_flow.py"], check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["version"] == __version__
    assert payload["generic_import_buttons_dispatch"] is True
    assert payload["modal_qfiledialog_exec_removed_from_phase_workbench"] is True
    assert payload["msh_vtu_geology_import_supported"] is True
