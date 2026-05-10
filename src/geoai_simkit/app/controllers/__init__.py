from __future__ import annotations

"""GUI controller helpers.

Controllers are intentionally thin: they translate user actions into calls to
headless services/modules and keep Qt widgets out of business logic.
"""

from .boundary_actions import BoundaryConditionActionController
from .geotechnical_actions import GeotechnicalActionController
from .gpu_runtime_actions import GpuRuntimeActionController
from .gui_slimming_actions import GuiSlimmingActionController
from .material_actions import MaterialMappingActionController
from .mesh_actions import MeshActionController
from .module_governance_actions import ModuleGovernanceActionController
from .plugin_entry_point_actions import PluginEntryPointActionController
from .project_actions import ProjectActionController
from .project_workflow import ProjectWorkflowController
from .result_actions import ResultActionController
from .solver_actions import SolverActionController
from .stage_actions import StageActionController
from .workflow_artifact_actions import WorkflowArtifactActionController
from .workflow_controller import run_headless_project_workflow

from .geometry_actions import GeometryActionController
from .export_actions import ExportActionController
from .compute_preference_actions import ComputePreferenceActionController
from .mesher_backend_actions import MesherBackendActionController
from .meshing_validation_actions import MeshingValidationActionController
from .quality_gate_actions import QualityGateActionController
__all__ = [
    "QualityGateActionController",
    "MesherBackendActionController",
    "MeshingValidationActionController",
    "ComputePreferenceActionController",
    "ExportActionController",
    "GeometryActionController",
    "BoundaryConditionActionController",
    "GeotechnicalActionController",
    "GpuRuntimeActionController",
    "GuiSlimmingActionController",
    "MaterialMappingActionController",
    "MeshActionController",
    "ModuleGovernanceActionController",
    "PluginEntryPointActionController",
    "ProjectActionController",
    "ProjectWorkflowController",
    "ResultActionController",
    "SolverActionController",
    "StageActionController",
    "WorkflowArtifactActionController",
    "run_headless_project_workflow",
]
