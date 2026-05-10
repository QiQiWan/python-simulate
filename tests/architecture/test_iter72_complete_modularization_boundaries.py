from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.app.controllers.module_kernel_actions import ModuleKernelActionController
from geoai_simkit.services.module_kernel import build_complete_modularization_report

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module)
    return imports


def test_modularity_contracts_are_dependency_light() -> None:
    imports = _imports(ROOT / "contracts" / "modularity.py")
    forbidden = {
        "geoai_simkit.app",
        "geoai_simkit.solver",
        "geoai_simkit.mesh",
        "geoai_simkit.geoproject",
        "PySide6",
        "pyvista",
        "warp",
    }
    assert not (imports & forbidden)


def test_module_kernel_service_is_headless_and_uses_public_governance() -> None:
    imports = _imports(ROOT / "services" / "module_kernel.py")
    forbidden_prefixes = (
        "geoai_simkit.app",
        "PySide6",
        "pyvista",
        "warp",
        "geoai_simkit.geoproject.runtime_solver",
    )
    assert not any(any(item == prefix or item.startswith(prefix + ".") for prefix in forbidden_prefixes) for item in imports)


def test_module_kernel_action_controller_is_qt_free() -> None:
    imports = _imports(ROOT / "app" / "controllers" / "module_kernel_actions.py")
    assert "PySide6" not in imports
    assert "pyvista" not in imports
    assert "warp" not in imports
    controller = ModuleKernelActionController(metadata={"panel": "architecture"})
    report = controller.complete_modularization_report()
    assert report["ok"] is True
    assert report["metadata"]["panel"] == "architecture"
    rows = controller.module_manifest_rows()
    assert rows
    assert all(row["entrypoint_count"] > 0 for row in rows)


def test_complete_modularization_report_keeps_legacy_islands_explicit() -> None:
    report = build_complete_modularization_report().to_dict()
    legacy_paths = {row["path"] for row in report["legacy_boundaries"]}
    assert "app/main_window_impl.py" in legacy_paths
    assert "services/legacy_gui_backends.py" in legacy_paths
    assert report["metadata"]["gui_slimming"]["ok"] is True
