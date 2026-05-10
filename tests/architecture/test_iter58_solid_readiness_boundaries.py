from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_solid_readiness_gate_is_dependency_light() -> None:
    imports = _imports(Path("src/geoai_simkit/mesh/solid_readiness.py"))
    banned = {"pyvista", "gmsh", "meshio", "warp", "PySide6"}
    assert not any(name.split(".")[0] in banned for name in imports)


def test_stl_volume_generators_are_registered_and_described() -> None:
    from geoai_simkit.modules import module_plugin_catalog

    rows = module_plugin_catalog()["mesh_generators"]
    keys = {row["key"] for row in rows}
    assert {"voxel_hex8_from_stl", "gmsh_tet4_from_stl"}.issubset(keys)
    gmsh_row = next(row for row in rows if row["key"] == "gmsh_tet4_from_stl")
    assert "health" in gmsh_row
    assert "dependencies" in gmsh_row["health"]
