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


def test_geometry_kernel_service_still_lazy_loads_gmsh_meshio() -> None:
    imports = _imports("src/geoai_simkit/services/geometry_kernel.py")
    assert "gmsh" not in imports
    assert "meshio" not in imports
    assert "PySide6" not in imports


def test_operation_logging_diagnostics_layer_is_dependency_light() -> None:
    imports = _imports("src/geoai_simkit/diagnostics/operation_log.py")
    forbidden = {"gmsh", "meshio", "PySide6", "pyvista", "geoai_simkit.app", "geoai_simkit.solver"}
    assert not (imports & forbidden)


def test_geometry_kernel_controller_exposes_production_actions_without_optional_imports() -> None:
    imports = _imports("src/geoai_simkit/app/controllers/geometry_kernel_actions.py")
    forbidden = {"gmsh", "meshio", "PySide6", "pyvista", "geoai_simkit.solver.runtime_solver"}
    assert not (imports & forbidden)


def test_gmsh_occ_generator_is_registered_in_default_catalog() -> None:
    from geoai_simkit.modules import meshing

    assert "gmsh_occ_fragment_tet4_from_stl" in meshing.supported_mesh_generators()
    status = meshing.geometry_operation_log_status()
    assert status["metadata"]["contract"] == "geometry_log_status_v1"
