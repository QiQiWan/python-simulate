from __future__ import annotations

import json

from geoai_simkit.contracts import ModuleOptimizationPlan, ModuleOptimizationReadinessReport, ModuleOptimizationTarget
from geoai_simkit.services import build_module_governance_report
from geoai_simkit.services.module_optimization import (
    build_module_optimization_plan,
    build_module_optimization_readiness_report,
    module_optimization_targets,
)


def test_module_optimization_readiness_report_is_complete_and_serializable() -> None:
    report = build_module_optimization_readiness_report()
    assert isinstance(report, ModuleOptimizationReadinessReport)
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["version"] == "module_optimization_readiness_v1"
    assert payload["target_count"] >= 8
    assert payload["ready_count"] == payload["target_count"]
    assert payload["average_readiness_score"] >= 0.7
    assert "meshing" in payload["recommended_sequence"]
    json.dumps(payload, sort_keys=True)


def test_module_optimization_targets_expose_contracts_plugins_and_actions() -> None:
    targets = {target.module_key: target for target in module_optimization_targets()}
    assert {"meshing", "fem_solver", "geotechnical", "gui_modeling"} <= set(targets)
    meshing = targets["meshing"]
    assert isinstance(meshing, ModuleOptimizationTarget)
    assert meshing.ready is True
    assert "mesh_generators" in meshing.plugin_groups
    assert meshing.recommended_next_actions
    assert any(metric.key == "plugin_coverage" and metric.ok for metric in meshing.metrics)


def test_build_module_specific_optimization_plan_for_solver() -> None:
    plan = build_module_optimization_plan("fem_solver", focus="nonlinear_core")
    assert isinstance(plan, ModuleOptimizationPlan)
    payload = plan.to_dict()
    assert payload["ready"] is True
    assert payload["module_key"] == "fem_solver"
    assert "solver_backends" in payload["plugin_groups"]
    assert payload["steps"]
    assert any("nonlinear" in check.lower() or "backend" in check.lower() for check in payload["acceptance_criteria"])
    json.dumps(payload, sort_keys=True)


def test_module_governance_embeds_module_optimization_readiness() -> None:
    governance = build_module_governance_report().to_dict()
    readiness = governance["metadata"]["module_optimization_readiness"]
    assert readiness["ok"] is True
    assert readiness["metadata"]["architecture_status"] == "module_optimization_ready"
    assert readiness["target_count"] >= 8
