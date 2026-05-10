from __future__ import annotations

from typing import Any
from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, LoadDefinition
from geoai_simkit.pipeline.specs import BoundaryConditionSpec, ExcavationStepSpec, LoadSpec, StageSpec

def resolve_boundary_condition_spec(item: Any) -> BoundaryCondition:
    if isinstance(item, BoundaryCondition):
        return item
    return BoundaryCondition(str(getattr(item, 'name', 'bc')), str(getattr(item, 'kind', 'displacement')), str(getattr(item, 'target', 'boundary')), tuple(getattr(item, 'components', (0,1,2))), tuple(float(v) for v in getattr(item, 'values', (0.0,0.0,0.0))), dict(getattr(item, 'metadata', {}) or {}))

def resolve_load_spec(item: Any) -> LoadDefinition:
    if isinstance(item, LoadDefinition):
        return item
    return LoadDefinition(str(getattr(item, 'name', 'load')), str(getattr(item, 'kind', 'body')), str(getattr(item, 'target', 'domain')), tuple(float(v) for v in getattr(item, 'values', (0.0,0.0,0.0))), dict(getattr(item, 'metadata', {}) or {}))

def resolve_stage_spec(model: Any, spec: StageSpec) -> AnalysisStage:
    return AnalysisStage(
        name=str(spec.name),
        activate_regions=tuple(spec.activate_regions), deactivate_regions=tuple(spec.deactivate_regions),
        boundary_conditions=tuple(resolve_boundary_condition_spec(x) for x in tuple(spec.boundary_conditions or ())),
        loads=tuple(resolve_load_spec(x) for x in tuple(spec.loads or ())),
        metadata={**dict(spec.metadata or {}), **({'predecessor': spec.predecessor} if getattr(spec, 'predecessor', None) else {})},
    )

def resolve_excavation_steps(steps: tuple[ExcavationStepSpec, ...] | list[ExcavationStepSpec]):
    return tuple(steps or ())

def build_stage_sequence_from_excavation(model: Any, steps, initial_metadata: dict[str, Any] | None = None):
    regions = tuple(model.list_region_names()) if hasattr(model, 'list_region_names') else ()
    stages = [AnalysisStage('initial', activate_regions=regions, metadata=dict(initial_metadata or {}))]
    predecessor = 'initial'
    active = set(regions)
    for step in tuple(steps or ()): 
        for name in tuple(getattr(step, 'activate_regions', ()) or ()): active.add(str(name))
        for name in tuple(getattr(step, 'deactivate_regions', ()) or ()): active.discard(str(name))
        meta = dict(getattr(step, 'metadata', {}) or {})
        meta['activation_map'] = {r: (r in active) for r in regions}
        stages.append(AnalysisStage(str(getattr(step, 'name', 'stage')), activate_regions=tuple(getattr(step, 'activate_regions', ()) or ()), deactivate_regions=tuple(getattr(step, 'deactivate_regions', ()) or ()), boundary_conditions=tuple(resolve_boundary_condition_spec(x) for x in tuple(getattr(step, 'boundary_conditions', ()) or ())), loads=tuple(resolve_load_spec(x) for x in tuple(getattr(step, 'loads', ()) or ())), metadata={**meta, 'predecessor': predecessor}))
        predecessor = str(getattr(step, 'name', 'stage'))
    return stages

def build_node_pair_contact(*args, **kwargs):
    return {'kind': 'node_pair_contact', 'pairs': [], 'metadata': dict(kwargs)}
