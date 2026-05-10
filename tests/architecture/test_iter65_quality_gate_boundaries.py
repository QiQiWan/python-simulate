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


def test_quality_gate_service_is_headless_and_gui_free() -> None:
    imports = _imports(Path("src/geoai_simkit/services/quality_gates.py"))
    forbidden = {"PySide6", "pyvista", "warp", "geoai_simkit.app"}
    assert not (imports & forbidden)


def test_new_gui_controllers_route_through_services_or_modules_only() -> None:
    for name in ["geometry_actions.py", "compute_preference_actions.py", "mesher_backend_actions.py", "quality_gate_actions.py"]:
        imports = _imports(Path("src/geoai_simkit/app/controllers") / name)
        assert "PySide6" not in imports
        assert "pyvista" not in imports
        assert "geoai_simkit.geometry.mesh_engine" not in imports
        assert "geoai_simkit.solver.warp_backend" not in imports
