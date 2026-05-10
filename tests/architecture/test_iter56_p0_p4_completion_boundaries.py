from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _py_files(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


def test_workflow_service_is_headless_and_does_not_import_implementation_internals() -> None:
    path = ROOT / "services" / "workflow_service.py"
    imports = _imports(path)
    forbidden_prefixes = (
        "geoai_simkit.app",
        "geoai_simkit.geometry",
        "geoai_simkit.geoproject",
        "geoai_simkit.solver",
        "geoai_simkit.fem",
        "geoai_simkit.post",
        "geoai_simkit.results",
        "geoai_simkit.mesh",
        "geoai_simkit.stage",
    )
    offenders = sorted(item for item in imports if item.startswith(forbidden_prefixes))
    assert offenders == []


def test_app_workflow_controller_is_thin_service_wrapper() -> None:
    path = ROOT / "app" / "controllers" / "workflow_controller.py"
    text = path.read_text(encoding="utf-8")
    imports = _imports(path)
    assert "geoai_simkit.services" in imports
    assert "geoai_simkit.solver" not in imports
    assert "geoai_simkit.mesh" not in imports
    assert "def run_headless_project_workflow" in text


def test_contracts_export_workflow_and_project_port_capabilities_without_gui_imports() -> None:
    forbidden: list[str] = []
    for path in _py_files("contracts"):
        for item in _imports(path):
            if item.startswith(("geoai_simkit.app", "PySide6", "pyvista", "warp")):
                forbidden.append(f"{path.relative_to(ROOT)} imports {item}")
    assert forbidden == []

    from geoai_simkit.contracts import ProjectPortCapabilities, ProjectWorkflowRequest, ProjectWorkflowReport, WorkflowStepReport

    assert ProjectPortCapabilities().to_dict()["readable"] is True
    assert ProjectWorkflowRequest is not None
    assert ProjectWorkflowReport is not None
    assert WorkflowStepReport is not None


def test_plugin_catalog_schema_validation_is_clean() -> None:
    from geoai_simkit.modules import module_plugin_catalog, validate_plugin_catalog

    report = validate_plugin_catalog(module_plugin_catalog())
    assert report["ok"] is True
    assert report["issue_count"] == 0
    assert set(report["registries"]) >= {
        "geology_importers",
        "mesh_generators",
        "stage_compilers",
        "solver_backends",
        "material_model_providers",
        "runtime_compilers",
        "postprocessors",
    }
