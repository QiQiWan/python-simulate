from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.modules import meshing
from geoai_simkit.solver.backend_registry import get_default_solver_backend_registry

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_iter60_mesh_region_helpers_are_dependency_light() -> None:
    imports = _imports(ROOT / "src" / "geoai_simkit" / "mesh" / "multi_region_stl.py")
    forbidden = {"pyvista", "gmsh", "meshio", "geoai_simkit.app"}
    assert not {name for name in imports for bad in forbidden if name == bad or name.startswith(bad + ".")}


def test_iter60_contact_readiness_is_gui_and_mesher_free() -> None:
    imports = _imports(ROOT / "src" / "geoai_simkit" / "solver" / "contact_readiness.py")
    forbidden = {"pyvista", "gmsh", "meshio", "PySide6", "geoai_simkit.app"}
    assert not {name for name in imports for bad in forbidden if name == bad or name.startswith(bad + ".")}


def test_iter60_registries_expose_conformal_and_nonlinear_plugins() -> None:
    assert "conformal_tet4_from_stl_regions" in meshing.supported_mesh_generators()
    assert "nonlinear_mohr_coulomb_cpu" in get_default_solver_backend_registry().keys()
