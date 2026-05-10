from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _py_files(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


def test_services_do_not_import_app_layer() -> None:
    offenders: list[str] = []
    for path in _py_files("services"):
        for item in _imports(path):
            if item.startswith("geoai_simkit.app"):
                offenders.append(f"{path.relative_to(ROOT)} imports {item}")
    assert offenders == []


def test_non_gui_modules_do_not_import_app_layer() -> None:
    offenders: list[str] = []
    for path in _py_files("modules"):
        if path.name == "gui_modeling.py":
            continue
        for item in _imports(path):
            if item.startswith("geoai_simkit.app"):
                offenders.append(f"{path.relative_to(ROOT)} imports {item}")
    assert offenders == []


def test_gui_split_modules_are_importable_without_qt() -> None:
    from geoai_simkit.app.controllers import ProjectWorkflowController
    from geoai_simkit.app.presenters import format_plugin_catalog_rows
    from geoai_simkit.app.view_models import ProjectStateViewModel

    assert ProjectWorkflowController is not None
    assert ProjectStateViewModel is not None
    assert format_plugin_catalog_rows({"x": [{"key": "demo", "available": True}]})[0]["available"] == "yes"
