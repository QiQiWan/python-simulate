from __future__ import annotations

from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.launcher_entry import _launcher_info


def test_iter165_version_and_launcher_path() -> None:
    assert __version__ == "1.6.6-runtime-action-smoke"
    info = _launcher_info(Path.cwd(), "start_gui.py")
    assert info["canonical_workbench_module"] == "geoai_simkit.app.shell.phase_workbench_qt"
    assert info["legacy_workbench_window_skipped"] is True


def test_historical_ribbon_is_startup_safe() -> None:
    source = Path("src/geoai_simkit/app/shell/phase_workbench_qt.py").read_text(encoding="utf-8")
    assert "self.ribbon.clear()" not in source
    assert "self.ribbon = None" in source
    assert "def _rebuild_ribbon" in source
    assert "Startup-safe no-op" in source or "startup-safe no-op" in source


def test_action_flow_checker_catches_ribbon_regression() -> None:
    from subprocess import run
    import json
    import sys

    proc = run([sys.executable, "tools/check_gui_action_flow.py"], check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["historical_ribbon_startup_safe"] is True
