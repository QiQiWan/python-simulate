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
from .complete_3d_mesh import build_complete_3d_mesh_report, project_3d_boundary_faces, supported_3d_mesh_generators, tag_project_3d_boundary_faces
from .workbench_phase_service import build_workbench_phase_state, build_workbench_phases, phase_toolbar_rows
from .geology_fem_analysis_workflow import (
    WORKFLOW_CONTRACT as IMPORTED_GEOLOGY_FEM_ANALYSIS_WORKFLOW_CONTRACT,
    build_imported_geology_result_view,
    check_imported_geology_fem_state,
    compile_imported_geology_solver_model,
    generate_or_repair_imported_geology_fem_mesh,
    prepare_imported_geology_for_fem,
    run_complete_imported_geology_fem_analysis,
    setup_automatic_stress_conditions,
    solve_imported_geology_to_steady_state,
)
from .geometry_kernel import build_geometry_kernel_report, build_soil_layer_volume_mesh, build_stratigraphic_surface_volume_mesh, geometry_kernel_dependency_status, gmsh_meshio_validation_report, build_gmsh_occ_fragment_tet4_mesh, geometry_operation_log_status, local_remesh_volume_mesh_quality, optimize_complex_stl_surface_mesh, optimize_stl_surface_mesh, optimize_volume_mesh_quality

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
    "build_workbench_phase_state",
    "build_workbench_phases",
    "phase_toolbar_rows",
    "run_project_workflow",
    "IMPORTED_GEOLOGY_FEM_ANALYSIS_WORKFLOW_CONTRACT",
    "build_imported_geology_result_view",
    "check_imported_geology_fem_state",
    "compile_imported_geology_solver_model",
    "generate_or_repair_imported_geology_fem_mesh",
    "prepare_imported_geology_for_fem",
    "run_complete_imported_geology_fem_analysis",
    "setup_automatic_stress_conditions",
    "solve_imported_geology_to_steady_state",
    "discover_external_plugin_entry_points",
    "load_external_plugins",
    "supported_external_plugin_group_dicts",
    "supported_external_plugin_groups",
    "analyze_stl_repair_readiness",
    "build_production_meshing_validation_report",
    "build_region_mesh_quality_summary",
    "optional_mesher_dependency_status",
    "validate_interface_conformity",
    "build_geometry_kernel_report",
    "build_soil_layer_volume_mesh",
    "geometry_kernel_dependency_status",
    "build_stratigraphic_surface_volume_mesh",
    "gmsh_meshio_validation_report",
    "build_gmsh_occ_fragment_tet4_mesh",
    "geometry_operation_log_status",
    "local_remesh_volume_mesh_quality",
    "optimize_complex_stl_surface_mesh",
    "optimize_volume_mesh_quality",
    "optimize_stl_surface_mesh",
    "build_complete_3d_mesh_report",
    "project_3d_boundary_faces",
    "supported_3d_mesh_generators",
    "tag_project_3d_boundary_faces",
    "build_geotechnical_quality_gate",
    "evaluate_material_compatibility",
    "evaluate_mesh_quality_gate",
    "run_stl_import_pipeline",
    "build_stl_import_wizard_payload",
    "analyze_stl_file",
    "STLImportWizardOptions",
]

from .quality_gates import build_geotechnical_quality_gate, evaluate_material_compatibility, evaluate_mesh_quality_gate

from .stl_import_pipeline import STLImportWizardOptions, analyze_stl_file, build_stl_import_wizard_payload, run_stl_import_pipeline
