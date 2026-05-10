from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_start_gui_smoke_entrypoint_builds_visual_workbench() -> None:
    pytest.importorskip("PySide6")
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run(
        [sys.executable, str(root / "start_gui.py"), "--smoke"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["entrypoint"] == "start_gui.py"
    assert report["diagnostics"]["gui_ready"] is True
    assert report["qt_application"]["available"] is True
    assert report["workbench_payload"]["available"] is True
    assert report["workbench_payload"]["contract"].startswith("unified_workbench_payload")
