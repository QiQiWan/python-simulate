from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    rows: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            rows.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            rows.add(node.module)
    return rows


def test_geometry_kernel_contracts_are_dependency_light() -> None:
    imports = _imports("src/geoai_simkit/contracts/geometry_kernel.py")
    forbidden = {"geoai_simkit.app", "geoai_simkit.solver", "geoai_simkit.mesh", "geoai_simkit.geoproject", "PySide6", "pyvista", "gmsh", "meshio"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_geometry_kernel_service_is_headless_and_optional_dependency_safe() -> None:
    imports = _imports("src/geoai_simkit/services/geometry_kernel.py")
    forbidden = {"geoai_simkit.app", "PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.geoproject.runtime_solver"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_geometry_kernel_controller_is_qt_free() -> None:
    imports = _imports("src/geoai_simkit/app/controllers/geometry_kernel_actions.py")
    forbidden = {"PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.solver", "geoai_simkit.geoproject.runtime_solver"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)
