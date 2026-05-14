from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import _launcher_info


def test_iter166_version_launcher_and_payload_contract() -> None:
    assert __version__ == "1.6.7-meshio-geology-import-empty-start"
    info = _launcher_info(Path.cwd(), "start_gui.py")
    assert info["contract"] == "geoai_simkit_gui_launcher_info_v7"
    assert info["canonical_workbench_module"] == "geoai_simkit.app.shell.phase_workbench_qt"
    assert info["legacy_workbench_window_skipped"] is True
    assert "runtime_button_smoke" in info["file_dialog_policy"]
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "phase_workbench_geometry_interaction_v15" in source
    assert "run_gui_button_smoke" in source


def test_runtime_button_smoke_implementation_present() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "self._gui_action_widgets" in source
    assert "button.setProperty(\"geoai_action_id\"" in source
    assert "def _run_gui_button_smoke_from_gui" in source
    assert "geoai_simkit_runtime_button_smoke_v1" in source
    assert "run_gui_button_smoke" in source
    for action in [
        "import_geology_model",
        "import_geology_auto",
        "import_structure_model",
        "import_structure_auto",
        "register_structure_box",
        "run_import_driven_assembly",
        "run_native_import_assembly",
        "assign_material_to_selection",
        "refresh_workbench_state",
    ]:
        assert action in source


def test_action_flow_checker_reports_runtime_smoke_ok() -> None:
    proc = subprocess.run([sys.executable, "tools/check_gui_action_flow.py"], check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["version"] == __version__
    assert payload["launcher_contract_v7"] is True
    assert payload["runtime_button_smoke_present"] is True
    assert payload["gui_action_widgets_tracked"] is True
    assert payload["production_actions_registered"] is True
