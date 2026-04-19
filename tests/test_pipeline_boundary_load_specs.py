from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.core.model import MaterialDefinition
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import (
    AnalysisCaseBuilder,
    AnalysisCaseSpec,
    AnalysisCaseValidator,
    BoundaryConditionSpec,
    GeometrySource,
    LoadSpec,
    MaterialAssignmentSpec,
    MeshAssemblySpec,
    RegionSelectorSpec,
    StageSpec,
    case_spec_from_dict,
    case_spec_to_dict,
)


def _selector_case() -> AnalysisCaseSpec:
    scene = ParametricPitScene(length=10.0, width=6.0, depth=6.0, soil_depth=10.0, nx=4, ny=3, nz=3, wall_thickness=0.4)
    params = {'length': scene.length, 'width': scene.width, 'depth': scene.depth, 'soil_depth': scene.soil_depth, 'nx': scene.nx, 'ny': scene.ny, 'nz': scene.nz, 'wall_thickness': scene.wall_thickness}
    return AnalysisCaseSpec(
        name='bc-load-selector-case',
        geometry=GeometrySource(kind='parametric_pit', parameters=params),
        mesh=MeshAssemblySpec(merge_points=True),
        material_library=(
            MaterialDefinition(name='soil_elastic', model_type='linear_elastic', parameters={'E': 1.0e7, 'nu': 0.3}),
            MaterialDefinition(name='wall_elastic', model_type='linear_elastic', parameters={'E': 3.0e10, 'nu': 0.2}),
        ),
        materials=(
            MaterialAssignmentSpec(selector=RegionSelectorSpec(patterns=('soil*',)), material_name='soil_elastic'),
            MaterialAssignmentSpec(selector=RegionSelectorSpec(names=('wall',)), material_name='wall_elastic'),
        ),
        boundary_conditions=(
            BoundaryConditionSpec(
                name='wall-cap-fix-z',
                kind='displacement',
                target='zmax',
                selector=RegionSelectorSpec(names=('wall',)),
                components=(2,),
                values=(0.0,),
            ),
        ),
        stages=(
            StageSpec(
                name='initial',
                loads=(
                    LoadSpec(
                        name='wall-cap-push',
                        kind='point_force',
                        target='zmax',
                        selector=RegionSelectorSpec(names=('wall',)),
                        values=(1.0e3, 0.0, 0.0),
                    ),
                ),
            ),
        ),
    )



def test_boundary_condition_spec_resolves_to_point_ids() -> None:
    prepared = AnalysisCaseBuilder(_selector_case()).build()
    bc = prepared.model.boundary_conditions[0]
    assert bc.target == 'point_ids'
    assert bc.metadata['point_id_space'] == 'global'
    assert bc.metadata['resolved_regions'] == ['wall']
    assert len(tuple(bc.metadata['point_ids'])) > 0



def test_stage_load_spec_resolves_to_point_ids() -> None:
    prepared = AnalysisCaseBuilder(_selector_case()).build()
    stage = prepared.model.stage_by_name('initial')
    assert stage is not None
    load = stage.loads[0]
    assert load.target == 'point_ids'
    assert load.metadata['point_id_space'] == 'global'
    assert load.metadata['resolved_regions'] == ['wall']
    assert len(tuple(load.metadata['point_ids'])) > 0



def test_case_roundtrip_preserves_boundary_and_load_specs() -> None:
    spec = _selector_case()
    payload = case_spec_to_dict(spec)
    restored = case_spec_from_dict(payload)
    assert isinstance(restored.boundary_conditions[0], BoundaryConditionSpec)
    assert isinstance(restored.stages[0].loads[0], LoadSpec)
    assert restored.boundary_conditions[0].selector is not None
    assert restored.stages[0].loads[0].selector is not None



def test_case_validator_reports_empty_boundary_and_load_selectors() -> None:
    spec = _selector_case()
    spec.boundary_conditions = (
        BoundaryConditionSpec(name='missing-bc', kind='displacement', target='all', selector=RegionSelectorSpec(patterns=('missing_*',))),
    )
    spec.stages = (
        StageSpec(name='initial', loads=(LoadSpec(name='missing-load', kind='point_force', target='all', selector=RegionSelectorSpec(patterns=('missing_*',)), values=(1.0, 0.0, 0.0)),)),
    )
    report = AnalysisCaseValidator(spec).validate()
    codes = {issue.code for issue in report.issues}
    assert 'boundary_selector_empty' in codes
    assert 'stage_load_selector_empty' in codes
    assert report.ok is True
