from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.services import build_gui_slimming_report, build_module_governance_report


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module)
    return imports


def test_main_window_legacy_geometry_solver_imports_are_extracted() -> None:
    imports = _absolute_imports(Path("src/geoai_simkit/app/main_window.py"))
    forbidden = {
        "geoai_simkit.geometry.ifc_import",
        "geoai_simkit.geometry.mesh_engine",
        "geoai_simkit.geometry.gmsh_mesher",
        "geoai_simkit.geometry.voxelize",
        "geoai_simkit.geometry.parametric",
        "geoai_simkit.post.exporters",
        "geoai_simkit.post.qt_viewport_events",
        "geoai_simkit.solver.compute_preferences",
        "geoai_simkit.solver.warp_backend",
        "geoai_simkit.solver.linear_algebra",
    }
    assert not (imports & forbidden)
    assert "geoai_simkit.services.legacy_gui_backends" in imports


def test_main_window_is_importable_without_optional_gui_backends() -> None:
    import geoai_simkit.app.main_window as main_window

    assert main_window.MainWindow is not None
    assert main_window.SolverSettings(backend="solid_linear_static_cpu").backend == "solid_linear_static_cpu"


def test_gui_slimming_direct_import_budget_is_zero() -> None:
    report = build_gui_slimming_report().to_dict()
    metric = report["metrics"][0]

    assert report["ok"] is True
    assert report["metadata"]["contract_version"] == "gui_slimming_report_v2"
    assert metric["direct_internal_import_count"] == 0
    assert metric["metadata"]["max_direct_internal_imports"] == 0
    assert report["controller_count"] >= 19


def test_module_governance_includes_v3_generation_metadata() -> None:
    report = build_module_governance_report().to_dict()

    assert report["ok"] is True
    assert report["metadata"]["governance_version"] == "module_boundary_v2"
    assert report["metadata"]["governance_generation"] == "module_boundary_v3"
