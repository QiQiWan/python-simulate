from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def test_production_meshing_validation_contracts_are_dependency_light() -> None:
    imports = _imports(Path("src/geoai_simkit/contracts/meshing_validation.py"))
    forbidden = {"PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.solver", "geoai_simkit.app"}
    assert not (imports & forbidden)


def test_production_meshing_validation_service_is_headless_and_optional_dependency_safe() -> None:
    imports = _imports(Path("src/geoai_simkit/services/production_meshing_validation.py"))
    forbidden = {"PySide6", "pyvista", "gmsh", "meshio", "warp", "geoai_simkit.app"}
    assert not (imports & forbidden)


def test_meshing_validation_controller_is_qt_free() -> None:
    imports = _imports(Path("src/geoai_simkit/app/controllers/meshing_validation_actions.py"))
    forbidden = {"PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.solver.runtime_solver"}
    assert not (imports & forbidden)
