from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "geoai_simkit"

MIGRATED_SERVICE_MODULES = (
    "blueprint_progress",
    "case_service",
    "job_service",
    "preprocess_service",
    "project_lifecycle",
    "results_service",
    "system_readiness",
    "validation_service",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_migrated_app_service_paths_are_thin_compatibility_wrappers() -> None:
    offenders: list[str] = []
    for module_name in MIGRATED_SERVICE_MODULES:
        path = ROOT / "app" / f"{module_name}.py"
        imports = _imports(path)
        allowed = {"__future__", f"geoai_simkit.services.{module_name}"}
        unexpected = sorted(item for item in imports if item not in allowed)
        text = path.read_text(encoding="utf-8")
        if unexpected:
            offenders.append(f"{path.relative_to(ROOT)} imports {unexpected}")
        if "class " in text or "@dataclass" in text:
            offenders.append(f"{path.relative_to(ROOT)} contains implementation code")
    assert offenders == []


def test_services_import_without_gui_frameworks() -> None:
    from geoai_simkit.services import (
        CaseService,
        JobService,
        PreprocessService,
        ProjectLifecycleManager,
        ResultsService,
        ValidationService,
    )

    assert CaseService is not None
    assert JobService is not None
    assert PreprocessService is not None
    assert ProjectLifecycleManager is not None
    assert ResultsService is not None
    assert ValidationService is not None
