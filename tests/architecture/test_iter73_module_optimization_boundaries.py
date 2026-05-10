from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.app.controllers.module_kernel_actions import ModuleKernelActionController
from geoai_simkit.app.controllers.module_optimization_actions import ModuleOptimizationActionController
from geoai_simkit.services.module_optimization import build_module_optimization_readiness_report

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


def test_optimization_contracts_are_dependency_light() -> None:
    imports = _imports(ROOT / "contracts" / "optimization.py")
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


def test_module_optimization_service_is_headless() -> None:
    imports = _imports(ROOT / "services" / "module_optimization.py")
    forbidden_prefixes = (
        "geoai_simkit.app",
        "PySide6",
        "pyvista",
        "warp",
        "geoai_simkit.geoproject.runtime_solver",
    )
    assert not any(any(item == prefix or item.startswith(prefix + ".") for prefix in forbidden_prefixes) for item in imports)
    report = build_module_optimization_readiness_report()
    assert report.ok is True


def test_module_optimization_action_controller_is_qt_free() -> None:
    imports = _imports(ROOT / "app" / "controllers" / "module_optimization_actions.py")
    assert "PySide6" not in imports
    assert "pyvista" not in imports
    assert "warp" not in imports
    controller = ModuleOptimizationActionController(metadata={"panel": "optimization"})
    report = controller.readiness_report()
    assert report["ok"] is True
    assert report["metadata"]["panel"] == "optimization"
    rows = controller.target_rows()
    assert rows
    assert any(row["module_key"] == "meshing" for row in rows)
    plan = controller.optimization_plan("meshing", focus="production_meshing")
    assert plan["module_key"] == "meshing"
    assert plan["steps"]


def test_module_kernel_controller_exposes_optimization_readiness() -> None:
    controller = ModuleKernelActionController(metadata={"panel": "architecture"})
    readiness = controller.module_optimization_readiness()
    assert readiness["ok"] is True
    assert readiness["metadata"]["panel"] == "architecture"
    assert readiness["ready_count"] == readiness["target_count"]
