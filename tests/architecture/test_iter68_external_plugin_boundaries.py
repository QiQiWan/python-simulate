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


def test_external_plugin_contracts_are_dependency_light():
    import geoai_simkit.contracts.plugins as plugins

    path = Path(plugins.__file__)
    imports = _imports(path)
    forbidden = {"PySide6", "pyvista", "warp", "geoai_simkit.app", "geoai_simkit.solver", "geoai_simkit.mesh"}
    assert not (imports & forbidden)


def test_plugin_entry_point_service_is_headless_and_no_app_dependency():
    import geoai_simkit.services.plugin_entry_points as service

    imports = _imports(Path(service.__file__))
    forbidden_prefixes = ("PySide6", "pyvista", "warp", "geoai_simkit.app")
    assert not [name for name in imports if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)]


def test_supported_external_plugin_groups_are_reported_in_governance():
    from geoai_simkit.services.module_governance import build_module_governance_report

    report = build_module_governance_report().to_dict()
    external = report["metadata"]["external_plugin_entry_points"]
    assert external["ok"]
    groups = {row["group"] for row in external["groups"]}
    assert "geoai_simkit.mesh_generators" in groups
    assert "geoai_simkit.solver_backends" in groups
    assert "geoai_simkit.postprocessors" in groups


def test_plugin_entry_point_controller_is_qt_free():
    import geoai_simkit.app.controllers.plugin_entry_point_actions as controller

    imports = _imports(Path(controller.__file__))
    assert "PySide6" not in imports
    assert "pyvista" not in imports
    assert "warp" not in imports
