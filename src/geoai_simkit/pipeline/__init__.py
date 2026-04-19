from .adjacency import RegionAdjacencyInfo, RegionBoundaryAdjacencyInfo, adjacency_summary_rows, compute_region_adjacency, compute_region_boundary_adjacency
from .builder import AnalysisCaseBuilder
from .execution import ExecutionPlan, build_execution_plan, build_solver_settings, recommended_thread_count
from .interfaces import register_interface_generator, registered_interface_generators, resolve_registered_interface_generator
from .io import CASE_FILE_KIND, CASE_FORMAT_VERSION, SUPPORTED_CASE_FORMAT_VERSIONS, case_spec_from_dict, case_spec_to_dict, load_case_spec, save_case_spec
from .preprocess import build_node_pair_contact, build_stage_sequence_from_excavation, resolve_boundary_condition_spec, resolve_excavation_steps, resolve_load_spec, resolve_stage_spec
from .preprocessor import PreprocessorArtifact, PreprocessorSnapshot, build_preprocessor_snapshot, save_preprocessor_snapshot
from .interface_ready import InterfaceReadyReport, apply_interface_node_split
from .interface_elements import InterfaceFaceElementGroup, InterfaceFaceElementPreview, InterfaceFaceElementSnapshot, compute_interface_face_elements, interface_element_definition_summary_rows, interface_face_element_summary_rows, interface_face_group_summary_rows, materialize_interface_face_definitions
from .runner import AnalysisExportSpec, AnalysisRunResult, AnalysisTaskSpec, GeneralFEMSolver
from geoai_simkit.runtime import CompileConfig, RuntimeCompiler, RuntimeConfig, SolverPolicy
from .selectors import collect_region_point_ids, resolve_region_selector, union_region_names
from .sources import geometry_source_from_ifc, geometry_source_from_mesh, geometry_source_from_mesh_file, geometry_source_from_parametric_pit, register_geometry_source, registered_geometry_sources, resolve_registered_geometry_source
from .specs import AnalysisCaseSpec, BoundaryConditionSpec, ContactPairSpec, ExcavationStepSpec, GeometrySource, InterfaceGeneratorSpec, LoadSpec, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, PreparedAnalysisCase, PreparationReport, RegionSelectorSpec, StageSpec, StructureGeneratorSpec
from .structures import register_structure_generator, registered_structure_generators, resolve_registered_structure_generator
from .surfaces import RegionBoundarySurfaceSummary, RegionSurfaceInterfaceCandidate, compute_region_boundary_surfaces, compute_region_surface_interface_candidates, interface_candidate_summary_rows, region_surface_summary_rows
from .topology import InterfaceNodeSplitPlan, InterfaceTopologyInfo, InterfaceTopologySnapshot, analyze_interface_topology, interface_node_split_summary_rows, interface_topology_summary_rows
from .validation import AnalysisCaseValidator, CaseValidationReport, ValidationIssue

__all__ = [
    'AnalysisCaseBuilder', 'AnalysisCaseSpec', 'AnalysisExportSpec', 'AnalysisRunResult', 'AnalysisTaskSpec',
    'CompileConfig', 'RuntimeCompiler', 'RuntimeConfig', 'SolverPolicy',
    'PreprocessorArtifact', 'PreprocessorSnapshot', 'InterfaceReadyReport', 'RegionAdjacencyInfo', 'RegionBoundaryAdjacencyInfo', 'RegionBoundarySurfaceSummary', 'RegionSurfaceInterfaceCandidate', 'InterfaceTopologyInfo', 'InterfaceNodeSplitPlan', 'InterfaceTopologySnapshot', 'InterfaceFaceElementPreview', 'InterfaceFaceElementGroup', 'InterfaceFaceElementSnapshot',
    'materialize_interface_face_definitions', 'interface_element_definition_summary_rows',
    'BoundaryConditionSpec',
    'AnalysisCaseValidator', 'CaseValidationReport', 'ValidationIssue', 'ContactPairSpec', 'ExcavationStepSpec',
    'ExecutionPlan', 'GeneralFEMSolver', 'GeometrySource', 'InterfaceGeneratorSpec', 'LoadSpec', 'MaterialAssignmentSpec', 'MeshAssemblySpec',
    'MeshPreparationSpec', 'PreparedAnalysisCase', 'PreparationReport', 'RegionSelectorSpec', 'StageSpec', 'StructureGeneratorSpec',
    'CASE_FILE_KIND', 'CASE_FORMAT_VERSION', 'SUPPORTED_CASE_FORMAT_VERSIONS',
    'adjacency_summary_rows', 'apply_interface_node_split', 'build_execution_plan', 'build_node_pair_contact', 'build_preprocessor_snapshot', 'save_preprocessor_snapshot', 'build_solver_settings', 'build_stage_sequence_from_excavation', 'compute_region_adjacency', 'compute_region_boundary_adjacency', 'compute_region_boundary_surfaces', 'compute_region_surface_interface_candidates', 'compute_interface_face_elements', 'analyze_interface_topology', 'interface_candidate_summary_rows', 'region_surface_summary_rows', 'interface_topology_summary_rows', 'interface_node_split_summary_rows', 'interface_face_element_summary_rows', 'interface_face_group_summary_rows',
    'case_spec_from_dict', 'case_spec_to_dict', 'geometry_source_from_ifc', 'geometry_source_from_mesh',
    'geometry_source_from_mesh_file', 'geometry_source_from_parametric_pit', 'load_case_spec',
    'recommended_thread_count', 'register_geometry_source', 'registered_geometry_sources', 'register_interface_generator', 'registered_interface_generators', 'register_structure_generator', 'registered_structure_generators',
    'collect_region_point_ids', 'union_region_names', 'resolve_boundary_condition_spec', 'resolve_load_spec',
    'resolve_excavation_steps', 'resolve_region_selector', 'resolve_registered_geometry_source', 'resolve_registered_interface_generator', 'resolve_registered_structure_generator', 'resolve_stage_spec',
    'save_case_spec',
]
