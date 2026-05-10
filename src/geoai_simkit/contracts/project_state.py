from __future__ import annotations

"""Project Port v3 engineering-state aggregate DTOs.

These DTOs keep GUI, workflow and reporting code from opening the legacy project
object when only engineering status is needed.  The helpers delegate to existing
Project Port summaries and geotechnical summaries, and return fully serializable
records suitable for workflow artifacts and readiness panels.
"""

from dataclasses import dataclass, field
from typing import Mapping

from .geotechnical import (
    AnalysisReadinessSummary,
    BoundaryConditionSummary,
    InterfaceSummary,
    LoadSummary,
    MaterialMappingSummary,
    SolidMeshSummary,
    StageActivationSummary,
    analysis_readiness_summary,
    boundary_condition_summary,
    interface_summary,
    load_summary,
    material_mapping_summary,
    solid_mesh_summary,
    stage_activation_summary,
)
from .project import (
    ProjectCompiledPhaseSummary,
    ProjectGeometrySummary,
    ProjectMaterialSummary,
    ProjectMeshSummary,
    ProjectReadPort,
    ProjectResultStoreSummary,
    ProjectStageSummary,
    project_compiled_phase_summary,
    project_geometry_summary,
    project_material_summary,
    project_mesh_summary,
    project_result_store_summary,
    project_stage_summary,
)


@dataclass(frozen=True, slots=True)
class ProjectGeometryState:
    summary: ProjectGeometrySummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"summary": self.summary.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectSolidMeshState:
    mesh: ProjectMeshSummary
    solid: SolidMeshSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.solid.solid_solver_ready)

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "mesh": self.mesh.to_dict(), "solid": self.solid.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectMaterialState:
    library: ProjectMaterialSummary
    mapping: MaterialMappingSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.mapping.ok)

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "library": self.library.to_dict(), "mapping": self.mapping.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectBoundaryState:
    boundary_conditions: BoundaryConditionSummary
    loads: LoadSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.boundary_conditions.has_constraints)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "boundary_conditions": self.boundary_conditions.to_dict(),
            "loads": self.loads.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectInterfaceState:
    interfaces: InterfaceSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.interfaces.contact_ready)

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "interfaces": self.interfaces.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectStageState:
    stages: ProjectStageSummary
    activation: StageActivationSummary
    compiled: ProjectCompiledPhaseSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "stages": self.stages.to_dict(),
            "activation": self.activation.to_dict(),
            "compiled": self.compiled.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectResultState:
    results: ProjectResultStoreSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"results": self.results.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectEngineeringState:
    geometry: ProjectGeometryState
    solid_mesh: ProjectSolidMeshState
    material: ProjectMaterialState
    boundary: ProjectBoundaryState
    interfaces: ProjectInterfaceState
    stages: ProjectStageState
    results: ProjectResultState
    readiness: AnalysisReadinessSummary
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.readiness.ready)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "geometry": self.geometry.to_dict(),
            "solid_mesh": self.solid_mesh.to_dict(),
            "material": self.material.to_dict(),
            "boundary": self.boundary.to_dict(),
            "interfaces": self.interfaces.to_dict(),
            "stages": self.stages.to_dict(),
            "results": self.results.to_dict(),
            "readiness": self.readiness.to_dict(),
            "metadata": {"contract": "project_engineering_state_v3", **dict(self.metadata)},
        }


def project_engineering_state(project_or_port: ProjectReadPort | object) -> ProjectEngineeringState:
    geometry = ProjectGeometryState(project_geometry_summary(project_or_port))
    mesh_summary = project_mesh_summary(project_or_port)
    solid = solid_mesh_summary(project_or_port)
    material = ProjectMaterialState(project_material_summary(project_or_port), material_mapping_summary(project_or_port))
    boundary = ProjectBoundaryState(boundary_condition_summary(project_or_port), load_summary(project_or_port))
    interfaces = ProjectInterfaceState(interface_summary(project_or_port))
    stages = ProjectStageState(project_stage_summary(project_or_port), stage_activation_summary(project_or_port), project_compiled_phase_summary(project_or_port))
    results = ProjectResultState(project_result_store_summary(project_or_port))
    readiness = analysis_readiness_summary(project_or_port)
    return ProjectEngineeringState(
        geometry=geometry,
        solid_mesh=ProjectSolidMeshState(mesh_summary, solid),
        material=material,
        boundary=boundary,
        interfaces=interfaces,
        stages=stages,
        results=results,
        readiness=readiness,
    )


__all__ = [
    "ProjectBoundaryState",
    "ProjectEngineeringState",
    "ProjectGeometryState",
    "ProjectInterfaceState",
    "ProjectMaterialState",
    "ProjectResultState",
    "ProjectSolidMeshState",
    "ProjectStageState",
    "project_engineering_state",
]
