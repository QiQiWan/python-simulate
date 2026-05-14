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


def test_mesh3d_contracts_are_dependency_light() -> None:
    imports = _imports("src/geoai_simkit/contracts/mesh3d.py")
    forbidden = {"geoai_simkit.app", "geoai_simkit.solver", "geoai_simkit.mesh", "geoai_simkit.geoproject", "PySide6", "pyvista", "gmsh", "meshio"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_complete_3d_mesh_service_is_headless_and_facade_safe() -> None:
    imports = _imports("src/geoai_simkit/services/complete_3d_mesh.py")
    forbidden = {"geoai_simkit.app", "PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.geoproject.runtime_solver"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_structured_3d_generators_do_not_depend_on_optional_meshers_or_gui() -> None:
    imports = _imports("src/geoai_simkit/mesh/structured_3d_generators.py")
    forbidden = {"geoai_simkit.app", "PySide6", "pyvista", "gmsh", "meshio"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_complete_3d_mesh_controller_is_qt_free() -> None:
    imports = _imports("src/geoai_simkit/app/controllers/complete_3d_mesh_actions.py")
    forbidden = {"PySide6", "pyvista", "gmsh", "meshio", "geoai_simkit.solver", "geoai_simkit.geoproject.runtime_solver"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)
