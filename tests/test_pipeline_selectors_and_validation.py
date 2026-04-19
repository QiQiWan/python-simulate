from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.core.model import MaterialDefinition
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, AnalysisCaseValidator, ContactPairSpec, GeometrySource, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec, RegionSelectorSpec, StageSpec


def _small_case() -> AnalysisCaseSpec:
    scene = ParametricPitScene(length=12.0, width=8.0, depth=8.0, soil_depth=12.0, nx=4, ny=3, nz=3, wall_thickness=0.5)
    return AnalysisCaseSpec(
        name='selector-case',
        geometry=GeometrySource(builder=scene.build),
        mesh=MeshAssemblySpec(merge_points=True),
        material_library=(
            MaterialDefinition(name='soil_elastic', model_type='linear_elastic', parameters={'E': 1.0e7, 'nu': 0.3}),
            MaterialDefinition(name='wall_elastic', model_type='linear_elastic', parameters={'E': 3.0e10, 'nu': 0.2}),
        ),
        materials=(
            MaterialAssignmentSpec(selector=RegionSelectorSpec(patterns=('soil*',)), material_name='soil_elastic'),
            MaterialAssignmentSpec(selector=RegionSelectorSpec(names=('wall',)), material_name='wall_elastic'),
        ),
        stages=(
            StageSpec(name='initial'),
            StageSpec(name='wall_activation', activate_selector=RegionSelectorSpec(names=('wall',))),
            StageSpec(name='excavate', deactivate_selector=RegionSelectorSpec(patterns=('soil_excavation_*',))),
        ),
        mesh_preparation=MeshPreparationSpec(contact_pairs=(ContactPairSpec(name='soil_wall', slave_selector=RegionSelectorSpec(names=('wall',)), master_selector=RegionSelectorSpec(names=('soil_mass',))),)),
    )


def test_region_selectors_expand_materials_and_stages() -> None:
    prepared = AnalysisCaseBuilder(_small_case()).build()
    model = prepared.model
    assigned = {binding.region_name: binding.material_name for binding in model.materials}
    assert assigned['wall'] == 'wall_elastic'
    assert assigned['soil_mass'] == 'soil_elastic'
    stage_lookup = {stage.name: stage for stage in model.stages}
    assert 'wall' in stage_lookup['wall_activation'].activate_regions
    assert 'soil_excavation_1' in stage_lookup['excavate'].deactivate_regions
    assert any(interface.name.startswith('soil_wall') for interface in model.interfaces)


def test_case_validator_reports_empty_selectors() -> None:
    case = _small_case()
    case.materials = (MaterialAssignmentSpec(selector=RegionSelectorSpec(patterns=('no_match_*',)), material_name='soil_elastic'),)
    report = AnalysisCaseValidator(case).validate()
    codes = {issue.code for issue in report.issues}
    assert 'material_selector_empty' in codes
    assert report.ok is True
