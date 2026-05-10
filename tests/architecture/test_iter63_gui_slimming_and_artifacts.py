from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.services import build_gui_slimming_report, build_module_governance_report


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module)
    return imports


def test_gui_slimming_report_tracks_main_window_budget_and_controller_growth() -> None:
    report = build_gui_slimming_report().to_dict()

    assert report["ok"] is True
    assert report["metadata"]["contract"] == "gui_slimming_report_v1"
    assert report["controller_count"] >= 14
    metric = report["metrics"][0]
    assert metric["path"] == "app/main_window.py"
    assert metric["line_count"] <= metric["max_lines"]
    assert metric["metadata"]["contract"] == "gui_slimming_budget_v1"


def test_workflow_artifact_controller_is_qt_free_and_implementation_light() -> None:
    path = Path("src/geoai_simkit/app/controllers/workflow_artifact_actions.py")
    imports = _absolute_imports(path)

    forbidden = {
        "PySide6",
        "pyvista",
        "warp",
        "geoai_simkit.solver",
        "geoai_simkit.geometry",
        "geoai_simkit.geoproject.runtime_solver",
    }
    assert not (imports & forbidden)
    assert "geoai_simkit.contracts" in imports


def test_module_governance_embeds_gui_slimming_status() -> None:
    report = build_module_governance_report().to_dict()

    assert report["ok"] is True
    assert report["metadata"]["governance_version"] == "module_boundary_v2"
    assert report["metadata"]["gui_slimming"]["ok"] is True
    assert report["metadata"]["gui_slimming"]["controller_count"] >= 14
