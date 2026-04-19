from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pyvista as pv

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, InterfaceDefinition, LoadDefinition, MaterialDefinition, StructuralElementDefinition


@dataclass(slots=True)
class GeometrySource:
    data: pv.DataSet | pv.MultiBlock | None = None
    builder: Callable[[], pv.DataSet | pv.MultiBlock] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def resolve(self) -> pv.DataSet | pv.MultiBlock:
        if self.data is not None:
            return self.data
        if self.builder is not None:
            return self.builder()
        if self.kind:
            from geoai_simkit.pipeline.sources import resolve_registered_geometry_source
            return resolve_registered_geometry_source(self.kind, self.parameters)
        raise ValueError('GeometrySource requires data, builder, or a registered kind.')


@dataclass(slots=True)
class RegionSelectorSpec:
    names: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    exclude_names: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()


@dataclass(slots=True)
class MeshAssemblySpec:
    element_family: str = 'auto'
    global_size: float = 2.0
    padding: float = 0.0
    merge_points: bool = True
    keep_geometry_copy: bool = True
    only_material_bound_geometry: bool = True
    local_refinement: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MaterialAssignmentSpec:
    region_names: tuple[str, ...] = ()
    selector: RegionSelectorSpec | None = None
    material_name: str = ''
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)



@dataclass(slots=True)
class BoundaryConditionSpec:
    name: str
    kind: str
    target: str = 'all'
    region_names: tuple[str, ...] = ()
    selector: RegionSelectorSpec | None = None
    components: tuple[int, ...] = (0, 1, 2)
    values: tuple[float, ...] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoadSpec:
    name: str
    kind: str
    target: str = 'all'
    region_names: tuple[str, ...] = ()
    selector: RegionSelectorSpec | None = None
    values: tuple[float, ...] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StageSpec:
    name: str
    predecessor: str | None = None
    activation_map: dict[str, bool] | None = None
    activate_regions: tuple[str, ...] = ()
    deactivate_regions: tuple[str, ...] = ()
    activate_selector: RegionSelectorSpec | None = None
    deactivate_selector: RegionSelectorSpec | None = None
    boundary_conditions: tuple[BoundaryCondition | BoundaryConditionSpec, ...] = ()
    loads: tuple[LoadDefinition | LoadSpec, ...] = ()
    steps: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_analysis_stage(self) -> AnalysisStage:
        meta = dict(self.metadata)
        if self.predecessor:
            meta['predecessor'] = str(self.predecessor)
        if self.activation_map is not None:
            meta['activation_map'] = {str(k): bool(v) for k, v in self.activation_map.items()}
        return AnalysisStage(
            name=self.name,
            activate_regions=tuple(self.activate_regions),
            deactivate_regions=tuple(self.deactivate_regions),
            boundary_conditions=tuple(self.boundary_conditions),
            loads=tuple(self.loads),
            steps=self.steps,
            metadata=meta,
        )


@dataclass(slots=True)
class ExcavationStepSpec:
    name: str
    deactivate_regions: tuple[str, ...] = ()
    activate_regions: tuple[str, ...] = ()
    deactivate_selector: RegionSelectorSpec | None = None
    activate_selector: RegionSelectorSpec | None = None
    steps: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContactPairSpec:
    name: str
    slave_region: str = ''
    master_region: str = ''
    slave_selector: RegionSelectorSpec | None = None
    master_selector: RegionSelectorSpec | None = None
    active_stages: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    search_radius_factor: float = 1.75
    exact_only: bool = False






@dataclass(slots=True)
class InterfaceGeneratorSpec:
    kind: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class StructureGeneratorSpec:
    kind: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MeshPreparationSpec:
    excavation_steps: tuple[ExcavationStepSpec, ...] = ()
    contact_pairs: tuple[ContactPairSpec, ...] = ()
    auto_interface_detection: bool = True
    merge_coincident_points: bool = True
    interface_node_split_mode: str = 'plan'
    interface_duplicate_side: str = 'slave'
    interface_element_mode: str = 'explicit'
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisCaseSpec:
    name: str
    geometry: GeometrySource
    mesh: MeshAssemblySpec = field(default_factory=MeshAssemblySpec)
    materials: tuple[MaterialAssignmentSpec, ...] = ()
    stages: tuple[StageSpec, ...] = ()
    mesh_preparation: MeshPreparationSpec = field(default_factory=MeshPreparationSpec)
    material_library: tuple[MaterialDefinition, ...] = ()
    boundary_conditions: tuple[BoundaryCondition | BoundaryConditionSpec, ...] = ()
    structures: tuple[StructuralElementDefinition | StructureGeneratorSpec, ...] = ()
    interfaces: tuple[InterfaceDefinition | InterfaceGeneratorSpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PreparationReport:
    merged_points: bool
    merged_point_count: int
    generated_stages: tuple[str, ...]
    generated_interfaces: tuple[str, ...]
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PreparedAnalysisCase:
    model: Any
    report: PreparationReport
