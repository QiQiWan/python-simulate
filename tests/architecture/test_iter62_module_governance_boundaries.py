from __future__ import annotations

import ast
from pathlib import Path

from geoai_simkit.app.controllers import ModuleGovernanceActionController
from geoai_simkit.modules import run_project_module_smokes
from geoai_simkit.services import audit_import_boundaries, build_module_governance_report

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def test_module_governance_report_is_clean_and_includes_geotechnical_facade() -> None:
    report = build_module_governance_report()
    payload = report.to_dict()

    assert payload["ok"] is True
    assert payload["module_count"] >= 8
    assert "geotechnical" in payload["public_module_keys"]
    assert payload["boundary_audit"]["violation_count"] == 0
    assert payload["registry_counts"]["mesh_generators"] >= 5
    assert payload["registry_counts"]["solver_backends"] >= 5


def test_boundary_governance_service_is_headless_and_does_not_import_app() -> None:
    imports = _imports("src/geoai_simkit/services/module_governance.py")
    forbidden = {"geoai_simkit.app", "PySide6", "pyvista", "warp"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)
    assert audit_import_boundaries().ok is True


def test_geotechnical_module_facade_does_not_import_gui_or_solver_implementation() -> None:
    imports = _imports("src/geoai_simkit/modules/geotechnical.py")
    forbidden = {
        "geoai_simkit.app",
        "geoai_simkit.solver.hex8_global",
        "geoai_simkit.geoproject.runtime_solver",
        "geoai_simkit.geometry.mesh_engine",
        "PySide6",
        "pyvista",
    }
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)


def test_module_governance_controller_is_qt_free() -> None:
    imports = _imports("src/geoai_simkit/app/controllers/module_governance_actions.py")
    forbidden = {"PySide6", "pyvista", "warp", "geoai_simkit.geoproject.runtime_solver"}
    assert not any(item == bad or item.startswith(bad + ".") for item in imports for bad in forbidden)
    payload = ModuleGovernanceActionController(metadata={"source": "test"}).governance_report()
    assert payload["ok"] is True
    assert payload["metadata"]["source"] == "test"


def test_project_module_smokes_include_geotechnical_module() -> None:
    report = run_project_module_smokes()
    assert report["ok"] is True
    modules = {row.get("key", row.get("module")) for row in report["checks"]}
    assert "geotechnical" in modules
