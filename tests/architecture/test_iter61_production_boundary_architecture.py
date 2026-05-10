from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.modules.plugin_catalog import module_plugin_catalog, validate_plugin_catalog

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_geotechnical_contracts_do_not_import_gui_or_solver_implementations() -> None:
    imports = _imports("src/geoai_simkit/contracts/geotechnical.py")
    forbidden = {"geoai_simkit.app", "geoai_simkit.solver", "geoai_simkit.geoproject", "PySide6", "pyvista"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_geotechnical_readiness_service_does_not_import_app_or_gui_frameworks() -> None:
    imports = _imports("src/geoai_simkit/services/geotechnical_readiness.py")
    forbidden = {"geoai_simkit.app", "PySide6", "pyvista", "warp"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_new_gui_controllers_are_qt_free_and_do_not_import_geometry_or_solver_internals() -> None:
    controller_files = [
        "src/geoai_simkit/app/controllers/material_actions.py",
        "src/geoai_simkit/app/controllers/boundary_actions.py",
        "src/geoai_simkit/app/controllers/geotechnical_actions.py",
    ]
    forbidden = {"PySide6", "pyvista", "geoai_simkit.geometry.mesh_engine", "geoai_simkit.geoproject.runtime_solver"}
    for file_name in controller_files:
        imports = _imports(file_name)
        assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden), file_name


def test_solver_catalog_exposes_production_boundary_backend() -> None:
    catalog = module_plugin_catalog()
    validation = validate_plugin_catalog(catalog)
    keys = {row["key"] for row in catalog["solver_backends"]}
    assert validation["ok"] is True
    assert "staged_mohr_coulomb_cpu" in keys
    row = next(item for item in catalog["solver_backends"] if item["key"] == "staged_mohr_coulomb_cpu")
    assert row["health"]["status"] == "production_boundary"
    assert "load_increments" in row["capabilities"]["features"]
