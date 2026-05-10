from __future__ import annotations

"""Module-level optimization readiness and planning service.

The complete modular architecture is useful only when individual modules can be
selected for deep optimization without destabilizing neighbors.  This service
turns module manifests, plugin registries and boundary markers into actionable
per-module optimization plans.
"""

from collections.abc import Iterable

from geoai_simkit.contracts.optimization import (
    ModuleOptimizationMetric,
    ModuleOptimizationPlan,
    ModuleOptimizationReadinessReport,
    ModuleOptimizationStep,
    ModuleOptimizationTarget,
)
from geoai_simkit.services.module_kernel import legacy_boundary_markers, module_manifests
from geoai_simkit.modules.plugin_catalog import module_plugin_catalog

_FOCUS_BY_MODULE: dict[str, str] = {
    "document_model": "Project Port schema and persistence safety",
    "geology_import": "STL/geology importer robustness and diagnostics",
    "meshing": "production mesh quality, STL repair and mesher plugins",
    "stage_planning": "phase activation, construction sequence and stage compiler coverage",
    "gui_modeling": "GUI shell/panel extraction and controller-driven interactions",
    "fem_solver": "solver kernel accuracy, nonlinear convergence and backend routing",
    "geotechnical": "engineering readiness, material/interface validation and staged workflows",
    "postprocessing": "typed result artifacts, reports and visualization handoff",
}

_ACTIONS_BY_MODULE: dict[str, tuple[str, ...]] = {
    "document_model": (
        "replace remaining legacy document unwraps with Project Port DTO helpers",
        "add migration tests for project schema/version compatibility",
        "define mutation transactions for material, stage and mesh updates",
    ),
    "geology_import": (
        "add importer-specific validation artifacts for STL/CSV/JSON sources",
        "harden multi-STL region identity and material metadata propagation",
        "expand malformed input fixtures and importer recovery tests",
    ),
    "meshing": (
        "validate production Gmsh/meshio paths in an optional dependency environment",
        "add mesh quality thresholds by solver backend and element family",
        "promote repair diagnostics to typed workflow artifacts",
    ),
    "stage_planning": (
        "add typed StageActivationState and stage diff artifacts",
        "expand stage compiler plugins for excavation/support sequencing",
        "validate stage dependency DAG and undo/redo invariants",
    ),
    "gui_modeling": (
        "continue splitting main_window_impl into shell, panels and presenters",
        "route every new GUI operation through Qt-free controllers",
        "add panel-level smoke tests that do not import solver internals",
    ),
    "fem_solver": (
        "separate solver input assembly from backend execution payloads",
        "add reference benchmark fixtures for linear, nonlinear and contact backends",
        "move preview nonlinear/contact cores toward global coupled residual assembly",
    ),
    "geotechnical": (
        "strengthen material compatibility gates per solver backend",
        "add verified 3D geotechnical benchmark scenarios",
        "connect staged nonlinear/contact reports to typed workflow manifests",
    ),
    "postprocessing": (
        "standardize result field schemas across linear, nonlinear and contact solvers",
        "add export package manifests and result lineage checks",
        "keep visualization backends lazy and behind postprocessor plugins",
    ),
}

_TESTS_BY_MODULE: dict[str, tuple[str, ...]] = {
    "document_model": ("tests/core/test_iter57_strict_port_and_backend.py", "tests/core/test_iter65*"),
    "geology_import": ("tests/core/test_iter58_stl_solid_pipeline.py", "tests/core/test_iter60_multi_stl_nonlinear_contact.py"),
    "meshing": ("tests/core/test_iter71_production_meshing_validation.py", "tests/architecture/test_iter71*"),
    "stage_planning": ("tests/visual_modeling/test_stage_activation_command_state_restore.py", "tests/core/test_iter58*"),
    "gui_modeling": ("tests/architecture/test_iter70_main_window_physical_slimming.py", "tests/architecture/test_iter63*"),
    "fem_solver": ("tools/run_core_fem_smoke.py", "tests/core/test_iter66_nonlinear_solver_core.py"),
    "geotechnical": ("tests/core/test_iter61*", "tests/core/test_iter67_contact_interface_solver.py"),
    "postprocessing": ("tests/core/test_iter63_typed_workflow_artifacts.py", "tests/workflow/*"),
}

_ACCEPTANCE_BY_MODULE: dict[str, tuple[str, ...]] = {
    "document_model": (
        "Project Port DTOs remain serializable and dependency-light",
        "legacy document bridge remains the only tolerated document unwrap island",
    ),
    "geology_import": (
        "malformed imports return diagnostics rather than partial silent state",
        "source region/material identity survives through mesh generation",
    ),
    "meshing": (
        "quality gate returns blocking issues before solver execution",
        "mesh plugins expose health/capability data and do not import GUI/runtime internals",
    ),
    "stage_planning": (
        "stage compiler output is stable through undo/redo and active block changes",
        "stage artifacts can be compared without opening solver internals",
    ),
    "gui_modeling": (
        "main_window.py remains a thin shell and direct_internal_import_count stays 0",
        "new GUI work is represented by Qt-free controllers and headless services",
    ),
    "fem_solver": (
        "all solver backends return SolveResult and plugin descriptors consistently",
        "nonlinear/contact diagnostics are written as typed artifacts and result fields",
    ),
    "geotechnical": (
        "readiness, material, contact and quality gates agree before staged solve",
        "benchmark scenarios can be run headless through geotechnical facade/workflow",
    ),
    "postprocessing": (
        "result packages preserve field names, lineage and solver metadata",
        "postprocessors remain lazily loaded and selectable by registry",
    ),
}

_SEQUENCE = (
    "meshing",
    "fem_solver",
    "geotechnical",
    "geology_import",
    "stage_planning",
    "postprocessing",
    "document_model",
    "gui_modeling",
)


def _plugin_counts_for_groups(groups: Iterable[str]) -> dict[str, int]:
    catalog = module_plugin_catalog()
    return {group: len(catalog.get(group, ())) for group in groups}


def _score_for_manifest(manifest, legacy_keys: tuple[str, ...]) -> tuple[float, tuple[ModuleOptimizationMetric, ...]]:
    interface = manifest.interface
    entrypoint_count = len(interface.entrypoints if interface else ())
    contract_count = len(interface.contracts if interface else ())
    plugin_counts = _plugin_counts_for_groups(interface.plugin_groups if interface else ())
    plugin_total = sum(plugin_counts.values())
    has_legacy = bool(legacy_keys)

    metrics = (
        ModuleOptimizationMetric(
            key="public_entrypoints",
            label="Public entrypoints",
            value=entrypoint_count,
            target=1,
            ok=entrypoint_count > 0,
            metadata={"module": manifest.key},
        ),
        ModuleOptimizationMetric(
            key="contract_count",
            label="Contract count",
            value=contract_count,
            target=1,
            ok=contract_count > 0 or manifest.key == "gui_modeling",
            metadata={"module": manifest.key},
        ),
        ModuleOptimizationMetric(
            key="plugin_coverage",
            label="Plugin coverage",
            value=plugin_total,
            target=1 if (interface and interface.plugin_groups) else 0,
            ok=plugin_total > 0 or not (interface and interface.plugin_groups),
            metadata={"groups": plugin_counts},
        ),
        ModuleOptimizationMetric(
            key="legacy_boundary_containment",
            label="Legacy boundary containment",
            value=len(legacy_keys),
            target=0,
            ok=not has_legacy or manifest.key == "gui_modeling" or manifest.key == "document_model",
            severity="warning" if has_legacy else "info",
            metadata={"legacy_boundaries": list(legacy_keys)},
        ),
    )
    raw = 0.0
    raw += 0.30 if entrypoint_count > 0 else 0.0
    raw += 0.25 if contract_count > 0 or manifest.key == "gui_modeling" else 0.0
    raw += 0.25 if plugin_total > 0 or not (interface and interface.plugin_groups) else 0.0
    raw += 0.20 if not has_legacy else (0.12 if manifest.key in {"gui_modeling", "document_model"} else 0.05)
    return round(raw, 3), metrics


def module_optimization_targets() -> tuple[ModuleOptimizationTarget, ...]:
    """Return optimization-ready targets for all public modules."""

    legacy_by_owner: dict[str, list[str]] = {}
    for marker in legacy_boundary_markers():
        legacy_by_owner.setdefault(marker.owner_module, []).append(marker.key)

    targets: list[ModuleOptimizationTarget] = []
    for manifest in module_manifests():
        interface = manifest.interface
        legacy_keys = tuple(sorted(legacy_by_owner.get(manifest.key, ())))
        score, metrics = _score_for_manifest(manifest, legacy_keys)
        ready = score >= 0.70 and all(metric.ok or metric.severity == "warning" for metric in metrics)
        targets.append(
            ModuleOptimizationTarget(
                module_key=manifest.key,
                label=manifest.label,
                responsibility=manifest.responsibility,
                ready=ready,
                readiness_score=score,
                primary_focus=_FOCUS_BY_MODULE.get(manifest.key, "module-specific performance and reliability"),
                owned_namespaces=tuple(manifest.owned_namespaces),
                public_entrypoints=tuple(interface.entrypoints if interface else ()),
                contract_names=tuple(interface.contracts if interface else ()),
                plugin_groups=tuple(interface.plugin_groups if interface else ()),
                service_entrypoints=tuple(interface.service_entrypoints if interface else ()),
                legacy_boundaries=legacy_keys,
                recommended_next_actions=_ACTIONS_BY_MODULE.get(manifest.key, ()),
                metrics=metrics,
                metadata={"contract": "module_optimization_target_v1"},
            )
        )
    return tuple(targets)


def build_module_optimization_readiness_report() -> ModuleOptimizationReadinessReport:
    """Build the global readiness report used to choose the next optimization target."""

    targets = module_optimization_targets()
    ready = tuple(target for target in targets if target.ready)
    avg = round(sum(target.readiness_score for target in targets) / len(targets), 3) if targets else 0.0
    known = {target.module_key for target in targets}
    sequence = tuple(key for key in _SEQUENCE if key in known)
    issues: list[str] = []
    if not targets:
        issues.append("no_module_optimization_targets")
    for target in targets:
        if not target.public_entrypoints:
            issues.append(f"module_missing_entrypoints:{target.module_key}")
    return ModuleOptimizationReadinessReport(
        ok=not issues and len(ready) == len(targets),
        target_count=len(targets),
        ready_count=len(ready),
        average_readiness_score=avg,
        targets=targets,
        recommended_sequence=sequence,
        issues=tuple(issues),
        warnings=tuple(
            f"contained_legacy_boundary:{target.module_key}" for target in targets if target.legacy_boundaries
        ),
        metadata={
            "contract": "module_optimization_readiness_report_v1",
            "architecture_status": "module_optimization_ready",
        },
    )


def build_module_optimization_plan(module_key: str, *, focus: str = "balanced") -> ModuleOptimizationPlan:
    """Return an actionable plan for optimizing one selected module."""

    targets = {target.module_key: target for target in module_optimization_targets()}
    try:
        target = targets[module_key]
    except KeyError as exc:
        known = ", ".join(sorted(targets))
        raise KeyError(f"Unknown optimization module {module_key!r}. Known modules: {known}") from exc

    steps: list[ModuleOptimizationStep] = []
    for index, action in enumerate(target.recommended_next_actions, start=1):
        steps.append(
            ModuleOptimizationStep(
                key=f"{module_key}.step_{index}",
                title=f"{target.label}: step {index}",
                layer="modules/services" if module_key != "gui_modeling" else "app.controllers/app.shell",
                action=action,
                expected_effect=f"Improves {target.primary_focus} while preserving public contracts.",
                acceptance_checks=_ACCEPTANCE_BY_MODULE.get(module_key, ()),
                risk="medium" if target.legacy_boundaries else "low",
                metadata={"module": module_key, "focus": focus},
            )
        )

    summary = (
        f"{target.label} is ready for isolated deep optimization. "
        f"Focus: {focus}; boundary readiness score {target.readiness_score:.2f}."
        if target.ready
        else f"{target.label} needs boundary cleanup before deep optimization."
    )
    return ModuleOptimizationPlan(
        module_key=module_key,
        focus=focus,
        ready=target.ready,
        summary=summary,
        target=target,
        steps=tuple(steps),
        required_contracts=target.contract_names,
        plugin_groups=target.plugin_groups,
        protected_boundaries=target.legacy_boundaries,
        recommended_tests=_TESTS_BY_MODULE.get(module_key, ()),
        acceptance_criteria=_ACCEPTANCE_BY_MODULE.get(module_key, ()),
        metadata={
            "contract": "module_optimization_plan_v1",
            "module": module_key,
            "focus": focus,
        },
    )


__all__ = [
    "build_module_optimization_plan",
    "build_module_optimization_readiness_report",
    "module_optimization_targets",
]
