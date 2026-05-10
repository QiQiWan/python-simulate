from __future__ import annotations

"""Headless application services used by GUI, CLI and automation entrypoints."""

from .case_service import CaseService, ModelBrowserSummary, StageBrowserRow
from .job_service import JobPlanSummary, JobRunSummary, JobService
from .preprocess_service import PreprocessOverview, PreprocessService
from .project_lifecycle import ProjectLifecycleManager
from .results_service import ResultsOverview, ResultsService
from .validation_service import ValidationOverview, ValidationService
from .workflow_service import ProjectWorkflowService, run_project_workflow
from .geotechnical_readiness import build_geotechnical_readiness_report
from .module_governance import audit_import_boundaries, build_module_governance_report, default_boundary_policy
from .gui_slimming import build_gui_slimming_report, main_window_slimming_metric
from .module_kernel import build_complete_modularization_report, legacy_boundary_markers, modular_layer_specs, module_dependency_edges, module_manifests
from .module_optimization import build_module_optimization_plan, build_module_optimization_readiness_report, module_optimization_targets
from .plugin_entry_points import discover_external_plugin_entry_points, load_external_plugins, supported_external_plugin_group_dicts, supported_external_plugin_groups
from .production_meshing_validation import analyze_stl_repair_readiness, build_production_meshing_validation_report, build_region_mesh_quality_summary, optional_mesher_dependency_status, validate_interface_conformity

__all__ = [
    "CaseService",
    "JobPlanSummary",
    "JobRunSummary",
    "JobService",
    "ModelBrowserSummary",
    "PreprocessOverview",
    "PreprocessService",
    "ProjectLifecycleManager",
    "ResultsOverview",
    "ResultsService",
    "StageBrowserRow",
    "ValidationOverview",
    "ValidationService",
    "ProjectWorkflowService",
    "audit_import_boundaries",
    "build_geotechnical_readiness_report",
    "build_gui_slimming_report",
    "build_module_governance_report",
    "default_boundary_policy",
    "build_module_optimization_plan",
    "build_module_optimization_readiness_report",
    "module_optimization_targets",
    "build_complete_modularization_report",
    "legacy_boundary_markers",
    "modular_layer_specs",
    "module_dependency_edges",
    "module_manifests",
    "main_window_slimming_metric",
    "run_project_workflow",
    "discover_external_plugin_entry_points",
    "load_external_plugins",
    "supported_external_plugin_group_dicts",
    "supported_external_plugin_groups",
    "analyze_stl_repair_readiness",
    "build_production_meshing_validation_report",
    "build_region_mesh_quality_summary",
    "optional_mesher_dependency_status",
    "validate_interface_conformity",
    "build_geotechnical_quality_gate",
    "evaluate_material_compatibility",
    "evaluate_mesh_quality_gate",
]

from .quality_gates import build_geotechnical_quality_gate, evaluate_material_compatibility, evaluate_mesh_quality_gate
