from __future__ import annotations

"""Headless GUI-slimming governance helpers.

The service does not import Qt or the main window module.  It statically inspects
source files so architecture tests and GUI status panels can track the migration
from a large legacy main window toward controller/service driven actions.
"""

import ast
from pathlib import Path
from typing import Iterable

from geoai_simkit.contracts.gui import GuiFileSlimmingMetric, GuiSlimmingReport

_GEOAI_ROOT = Path(__file__).resolve().parents[1]
_MAIN_WINDOW_PATH = _GEOAI_ROOT / "app" / "main_window.py"
_CONTROLLER_ROOT = _GEOAI_ROOT / "app" / "controllers"
_DEFAULT_MAIN_WINDOW_LINE_BUDGET = 4000
_DEFAULT_DIRECT_INTERNAL_IMPORT_BUDGET = 0
_LEGACY_DIRECT_IMPORT_PREFIXES = (
    "geoai_simkit.geometry",
    "geoai_simkit.solver",
    "geoai_simkit.post",
    "geoai_simkit.materials",
)


def _relative(path: Path) -> str:
    try:
        return path.relative_to(_GEOAI_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)
    return sorted(set(imports))


def _direct_internal_import_count(imports: Iterable[str]) -> int:
    count = 0
    for item in imports:
        if any(item == prefix or item.startswith(prefix + ".") for prefix in _LEGACY_DIRECT_IMPORT_PREFIXES):
            count += 1
    return count


def main_window_slimming_metric(max_lines: int = _DEFAULT_MAIN_WINDOW_LINE_BUDGET, max_direct_internal_imports: int = _DEFAULT_DIRECT_INTERNAL_IMPORT_BUDGET) -> GuiFileSlimmingMetric:
    """Return static line/import metrics for the legacy main window."""

    if not _MAIN_WINDOW_PATH.exists():
        return GuiFileSlimmingMetric(path="app/main_window.py", line_count=0, max_lines=max_lines, ok=False, metadata={"missing": True})
    text = _MAIN_WINDOW_PATH.read_text(encoding="utf-8")
    imports = _absolute_imports(_MAIN_WINDOW_PATH)
    direct_count = _direct_internal_import_count(imports)
    line_count = len(text.splitlines())
    return GuiFileSlimmingMetric(
        path=_relative(_MAIN_WINDOW_PATH),
        line_count=line_count,
        max_lines=max_lines,
        import_count=len(imports),
        direct_internal_import_count=direct_count,
        ok=line_count <= max_lines and direct_count <= max_direct_internal_imports,
        metadata={
            "contract": "gui_slimming_budget_v1",
            "contract_version": "gui_slimming_budget_v3",
            "implementation_module": "app/main_window_impl.py",
            "max_direct_internal_imports": int(max_direct_internal_imports),
            "legacy_direct_import_prefixes": list(_LEGACY_DIRECT_IMPORT_PREFIXES),
            "slimming_strategy": "new GUI actions must live in app.controllers and route through services/modules",
        },
    )


def build_gui_slimming_report(max_main_window_lines: int = _DEFAULT_MAIN_WINDOW_LINE_BUDGET, max_direct_internal_imports: int = _DEFAULT_DIRECT_INTERNAL_IMPORT_BUDGET) -> GuiSlimmingReport:
    """Build the GUI-slimming governance report."""

    metric = main_window_slimming_metric(max_lines=max_main_window_lines, max_direct_internal_imports=max_direct_internal_imports)
    controller_modules = tuple(sorted(_relative(path) for path in _CONTROLLER_ROOT.glob("*.py") if path.name != "__init__.py")) if _CONTROLLER_ROOT.exists() else ()
    warnings: list[str] = []
    if metric.direct_internal_import_count > max_direct_internal_imports:
        warnings.append("main_window_legacy_direct_internal_imports_remain")
    if metric.line_count > max_main_window_lines:
        warnings.append("main_window_line_budget_exceeded")
    return GuiSlimmingReport(
        ok=metric.ok,
        controller_count=len(controller_modules),
        metrics=(metric,),
        controller_modules=controller_modules,
        warnings=tuple(warnings),
        metadata={"contract": "gui_slimming_report_v1", "contract_version": "gui_slimming_report_v2",
            "physical_slimming_version": "gui_slimming_report_v3", "main_window_budget": max_main_window_lines, "direct_internal_import_budget": max_direct_internal_imports},
    )


__all__ = ["build_gui_slimming_report", "main_window_slimming_metric"]
