from __future__ import annotations

from dataclasses import replace

from geoai_simkit.examples.pit_example import build_demo_case
from geoai_simkit.pipeline import AnalysisCaseSpec, MeshAssemblySpec, StageSpec


def build_foundation_pit_showcase_case() -> AnalysisCaseSpec:
    base = build_demo_case()
    params = dict(base.geometry.parameters)
    params.update({
        'length': 42.0,
        'width': 24.0,
        'depth': 18.0,
        'soil_depth': 32.0,
        'nx': 14,
        'ny': 10,
        'nz': 9,
        'wall_thickness': 0.8,
    })
    mesh = replace(base.mesh, global_size=2.2, metadata={**dict(base.mesh.metadata), 'showcase_refinement': 'balanced'})
    stages = []
    for index, stage in enumerate(base.stages or (), start=1):
        metadata = dict(stage.metadata)
        metadata.setdefault('display_order', index)
        metadata.setdefault('visual_color_hint', ['#415a77', '#778da9', '#1b263b'][min(index - 1, 2)])
        metadata.setdefault('showcase_stage', True)
        stages.append(replace(stage, metadata=metadata))
    if not stages:
        stages = [
            StageSpec(name='initial', metadata={'display_order': 1, 'showcase_stage': True}),
            StageSpec(name='excavate_level_1', predecessor='initial', metadata={'display_order': 2, 'showcase_stage': True}),
            StageSpec(name='excavate_level_2', predecessor='excavate_level_1', metadata={'display_order': 3, 'showcase_stage': True}),
        ]
    metadata = dict(base.metadata)
    metadata.update({
        'demo_version': '0.7.0',
        'demo_kind': 'foundation_pit_showcase',
        'showcase': True,
        'default_view_mode': 'stage_activity',
        'display_title': 'Foundation Pit Showcase Demo',
        'display_subtitle': 'Built-in excavation, wall, support, and stage-activation example for visualization and workflow demos.',
    })
    case = replace(
        base,
        name='foundation-pit-showcase',
        geometry=replace(base.geometry, parameters=params, metadata={**dict(base.geometry.metadata), 'showcase': True}),
        mesh=mesh,
        stages=tuple(stages),
        metadata=metadata,
    )
    return case


__all__ = ['build_foundation_pit_showcase_case']
