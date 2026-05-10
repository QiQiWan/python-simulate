from __future__ import annotations

"""Headless module-boundary governance service.

This service scans source imports and plugin/module registries without importing
GUI frameworks or solver internals. It is intended for architecture tests, CLI
smokes and GUI status panels that need a single modularity health report.
"""

import ast
from pathlib import Path
from typing import Iterable

from geoai_simkit.contracts.boundary import (
    ImportBoundaryRule,
    ImportBoundaryViolation,
    ModuleBoundaryAuditReport,
    ModuleGovernanceReport,
)
from geoai_simkit.modules.plugin_catalog import external_plugin_entry_point_report, module_plugin_catalog, validate_plugin_catalog
from geoai_simkit.services.gui_slimming import build_gui_slimming_report
from geoai_simkit.modules.registry import PROJECT_MODULE_SPECS

_GEOAI_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FORBIDDEN_GUI = ("PySide6", "pyvista", "warp")


def _relative(path: Path) -> str:
    try:
        return path.relative_to(_GEOAI_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _py_files(path_prefix: str) -> list[Path]:
    base = _GEOAI_ROOT / path_prefix
    if base.is_file():
        return [base]
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.py") if path.is_file())


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module)
    return imports


def _matches_forbidden(import_name: str, forbidden: str) -> bool:
    return import_name == forbidden or import_name.startswith(forbidden + ".")


def default_boundary_policy() -> tuple[ImportBoundaryRule, ...]:
    """Return the current strict-but-compatible modularity policy."""

    return (
        ImportBoundaryRule(
            key="contracts_dependency_light",
            layer="contracts",
            path_prefix="contracts",
            forbidden_imports=(
                "geoai_simkit.app",
                "geoai_simkit.geoproject",
                "geoai_simkit.geometry",
                "geoai_simkit.mesh",
                "geoai_simkit.pipeline",
                "geoai_simkit.post",
                "geoai_simkit.results",
                "geoai_simkit.solver",
                *_DEFAULT_FORBIDDEN_GUI,
            ),
            description="Contracts remain dependency-light and must not import implementation layers.",
        ),
        ImportBoundaryRule(
            key="services_headless",
            layer="services",
            path_prefix="services",
            forbidden_imports=("geoai_simkit.app", *_DEFAULT_FORBIDDEN_GUI),
            description="Services are headless orchestration and must not import GUI frameworks or app code.",
        ),
        ImportBoundaryRule(
            key="modules_no_app_except_gui_modeling",
            layer="modules",
            path_prefix="modules",
            forbidden_imports=("geoai_simkit.app",),
            allow_files=("modules/gui_modeling.py",),
            description="Module facades do not depend on app except the explicit gui_modeling facade.",
        ),
        ImportBoundaryRule(
            key="solver_no_app",
            layer="solver",
            path_prefix="solver",
            forbidden_imports=("geoai_simkit.app",),
            description="Solver implementations must not import GUI/app code.",
        ),
        ImportBoundaryRule(
            key="mesh_no_app_or_solver",
            layer="mesh",
            path_prefix="mesh",
            forbidden_imports=("geoai_simkit.app", "geoai_simkit.geoproject.runtime_solver"),
            description="Mesh generators must not import GUI/app code or runtime solver internals.",
        ),
        ImportBoundaryRule(
            key="controllers_qt_free",
            layer="app.controllers",
            path_prefix="app/controllers",
            forbidden_imports=(
                "PySide6",
                "pyvista",
                "warp",
                "geoai_simkit.geoproject.runtime_solver",
                "geoai_simkit.geometry.mesh_engine",
                "geoai_simkit.solver.hex8_global",
            ),
            description="Qt-free action controllers route through services/facades rather than implementation internals.",
        ),
    )


def audit_import_boundaries(rules: Iterable[ImportBoundaryRule] | None = None) -> ModuleBoundaryAuditReport:
    """Scan the source tree for policy violations."""

    policy = tuple(default_boundary_policy() if rules is None else rules)
    violations: list[ImportBoundaryViolation] = []
    checked: set[str] = set()
    warnings: list[str] = []

    for rule in policy:
        files = _py_files(rule.path_prefix)
        if not files:
            warnings.append(f"rule {rule.key}: no files matched {rule.path_prefix!r}")
        allow = set(rule.allow_files)
        for path in files:
            rel = _relative(path)
            checked.add(rel)
            if rel in allow:
                continue
            try:
                imports = _absolute_imports(path)
            except SyntaxError as exc:  # pragma: no cover - defensive
                violations.append(
                    ImportBoundaryViolation(
                        rule_key=rule.key,
                        file=rel,
                        import_name="<syntax>",
                        layer=rule.layer,
                        reason=f"syntax_error:{exc}",
                    )
                )
                continue
            for import_name in sorted(imports):
                for forbidden in rule.forbidden_imports:
                    if _matches_forbidden(import_name, forbidden):
                        violations.append(
                            ImportBoundaryViolation(
                                rule_key=rule.key,
                                file=rel,
                                import_name=import_name,
                                layer=rule.layer,
                                reason=f"forbidden_import:{forbidden}",
                            )
                        )

    return ModuleBoundaryAuditReport(
        ok=not violations,
        rules=policy,
        checked_file_count=len(checked),
        violation_count=len(violations),
        violations=tuple(violations),
        warnings=tuple(warnings),
        metadata={"source_root": _GEOAI_ROOT.as_posix()},
    )


def build_module_governance_report() -> ModuleGovernanceReport:
    """Build a consolidated governance report for modularity status."""

    catalog = module_plugin_catalog()
    validation = validate_plugin_catalog(catalog)
    boundary = audit_import_boundaries()
    gui_slimming = build_gui_slimming_report()
    external_plugins = external_plugin_entry_point_report(load=False)
    from geoai_simkit.services.module_kernel import build_complete_modularization_report

    complete_modularization = build_complete_modularization_report(include_external_plugins=False)
    from geoai_simkit.services.module_optimization import build_module_optimization_readiness_report

    optimization_readiness = build_module_optimization_readiness_report()
    registry_counts = {key: len(value) for key, value in catalog.items()}
    public_module_keys = tuple(spec.key for spec in PROJECT_MODULE_SPECS)
    warnings: list[str] = []
    if not validation.get("ok"):
        warnings.append("plugin_catalog_contract_failed")
    warnings.extend(boundary.warnings)
    ok = bool(validation.get("ok")) and boundary.ok and gui_slimming.ok
    return ModuleGovernanceReport(
        ok=ok,
        module_count=len(PROJECT_MODULE_SPECS),
        registry_counts=registry_counts,
        public_module_keys=public_module_keys,
        boundary_audit=boundary,
        warnings=tuple(warnings),
        metadata={
            "plugin_validation": validation,
            "governance_version": "module_boundary_v2",
            "governance_generation": "module_boundary_v3",
            "gui_slimming": gui_slimming.to_dict(),
            "external_plugin_entry_points": external_plugins,
            "complete_modularization": complete_modularization.to_dict(),
            "module_optimization_readiness": optimization_readiness.to_dict(),
        },
    )


__all__ = ["audit_import_boundaries", "build_module_governance_report", "default_boundary_policy"]
