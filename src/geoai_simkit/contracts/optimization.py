from __future__ import annotations

"""Contracts for module-level deep optimization readiness.

These DTOs describe how an already-modular subsystem can be optimized in
isolation: public contract surface, plugin seams, validation checks, and legacy
bridges that must not leak into neighboring modules.  They remain
implementation-light so GUI panels, CI jobs and external tooling can read the
same optimization plan without importing solver, mesh, Qt or rendering code.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModuleOptimizationMetric:
    """One measurable property used to decide whether a module is optimization-ready."""

    key: str
    label: str
    value: object
    target: object | None = None
    ok: bool = True
    severity: str = "info"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "target": self.target,
            "ok": bool(self.ok),
            "severity": self.severity,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleOptimizationStep:
    """One concrete optimization step scoped to a single module."""

    key: str
    title: str
    layer: str
    action: str
    expected_effect: str
    acceptance_checks: tuple[str, ...] = ()
    risk: str = "low"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "layer": self.layer,
            "action": self.action,
            "expected_effect": self.expected_effect,
            "acceptance_checks": list(self.acceptance_checks),
            "risk": self.risk,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleOptimizationTarget:
    """A public module that can be optimized independently."""

    module_key: str
    label: str
    responsibility: str
    ready: bool
    readiness_score: float
    primary_focus: str
    owned_namespaces: tuple[str, ...] = ()
    public_entrypoints: tuple[str, ...] = ()
    contract_names: tuple[str, ...] = ()
    plugin_groups: tuple[str, ...] = ()
    service_entrypoints: tuple[str, ...] = ()
    legacy_boundaries: tuple[str, ...] = ()
    recommended_next_actions: tuple[str, ...] = ()
    metrics: tuple[ModuleOptimizationMetric, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "module_key": self.module_key,
            "label": self.label,
            "responsibility": self.responsibility,
            "ready": bool(self.ready),
            "readiness_score": float(self.readiness_score),
            "primary_focus": self.primary_focus,
            "owned_namespaces": list(self.owned_namespaces),
            "public_entrypoints": list(self.public_entrypoints),
            "contract_names": list(self.contract_names),
            "plugin_groups": list(self.plugin_groups),
            "service_entrypoints": list(self.service_entrypoints),
            "legacy_boundaries": list(self.legacy_boundaries),
            "recommended_next_actions": list(self.recommended_next_actions),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleOptimizationPlan:
    """Actionable plan for deep optimization of one module."""

    module_key: str
    focus: str
    ready: bool
    summary: str
    target: ModuleOptimizationTarget
    steps: tuple[ModuleOptimizationStep, ...] = ()
    required_contracts: tuple[str, ...] = ()
    plugin_groups: tuple[str, ...] = ()
    protected_boundaries: tuple[str, ...] = ()
    recommended_tests: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "module_key": self.module_key,
            "focus": self.focus,
            "ready": bool(self.ready),
            "summary": self.summary,
            "target": self.target.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "required_contracts": list(self.required_contracts),
            "plugin_groups": list(self.plugin_groups),
            "protected_boundaries": list(self.protected_boundaries),
            "recommended_tests": list(self.recommended_tests),
            "acceptance_criteria": list(self.acceptance_criteria),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleOptimizationReadinessReport:
    """System-level readiness report for selecting the next module to optimize."""

    ok: bool
    version: str = "module_optimization_readiness_v1"
    target_count: int = 0
    ready_count: int = 0
    average_readiness_score: float = 0.0
    targets: tuple[ModuleOptimizationTarget, ...] = ()
    recommended_sequence: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "version": self.version,
            "target_count": int(self.target_count),
            "ready_count": int(self.ready_count),
            "average_readiness_score": float(self.average_readiness_score),
            "targets": [target.to_dict() for target in self.targets],
            "recommended_sequence": list(self.recommended_sequence),
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "ModuleOptimizationMetric",
    "ModuleOptimizationPlan",
    "ModuleOptimizationReadinessReport",
    "ModuleOptimizationStep",
    "ModuleOptimizationTarget",
]
