from __future__ import annotations

import pytest

pytest.importorskip('pyvista')

from geoai_simkit.examples.pit_example import build_demo_case, build_demo_model
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, ContactPairSpec, ExcavationStepSpec, GeneralFEMSolver, GeometrySource, MaterialAssignmentSpec, MeshAssemblySpec, MeshPreparationSpec


def test_demo_case_prepares_through_general_pipeline() -> None:
    model = GeneralFEMSolver().prepare_case(build_demo_case()).model
    assert model.metadata.get('pipeline.case_name') == 'pit-demo'
    assert model.geometry_state() == 'meshed'
    assert model.get_region('soil_mass') is not None
    assert model.material_for_region('wall') is not None


def test_excavation_sequence_autogenerates_stage_activation_maps() -> None:
    scene = ParametricPitScene(length=8.0, width=4.0, depth=4.0, soil_depth=6.0, nx=4, ny=4, nz=4, wall_thickness=0.4)
    case = AnalysisCaseSpec(name='generic-excavation', geometry=GeometrySource(builder=scene.build), mesh=MeshAssemblySpec(merge_points=True), materials=(MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1e7, 'nu': 0.3}), MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3e10, 'nu': 0.2})), mesh_preparation=MeshPreparationSpec(excavation_steps=(ExcavationStepSpec(name='excavate_upper', deactivate_regions=('soil_excavation_1',), metadata={'stage_role': 'excavate_upper'}), ExcavationStepSpec(name='excavate_lower', deactivate_regions=('soil_excavation_2',), metadata={'stage_role': 'excavate_lower'}))))
    prepared = AnalysisCaseBuilder(case).build()
    assert [stage.name for stage in prepared.model.stages] == ['initial', 'excavate_upper', 'excavate_lower']
    assert prepared.model.stage_by_name('excavate_upper').metadata['activation_map']['soil_excavation_1'] is False
    assert prepared.model.stage_by_name('excavate_lower').metadata['activation_map']['soil_excavation_2'] is False


def test_generic_contact_pair_generation_produces_interfaces() -> None:
    demo_model = build_demo_model()
    case = AnalysisCaseSpec(name='generic-contacts', geometry=GeometrySource(data=demo_model.mesh), mesh=MeshAssemblySpec(merge_points=True), materials=(MaterialAssignmentSpec(region_names=('soil_mass', 'soil_excavation_1', 'soil_excavation_2'), material_name='linear_elastic', parameters={'E': 1e7, 'nu': 0.3}), MaterialAssignmentSpec(region_names=('wall',), material_name='linear_elastic', parameters={'E': 3e10, 'nu': 0.2})), mesh_preparation=MeshPreparationSpec(contact_pairs=(ContactPairSpec(name='wall_to_soil', slave_region='wall', master_region='soil_mass', active_stages=('initial', 'wall_activation')),)))
    prepared = AnalysisCaseBuilder(case).build()
    iface = next((item for item in prepared.model.interfaces if item.name == 'wall_to_soil'), None)
    assert iface is not None and len(iface.slave_point_ids) == len(iface.master_point_ids) and len(iface.slave_point_ids) > 0
    assert iface.metadata['source'] == 'generic_mesh_preparation'
