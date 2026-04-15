from __future__ import annotations

import numpy as np

from geoai_simkit.core.model import AnalysisStage, InterfaceDefinition, SimulationModel, StructuralElementDefinition
from geoai_simkit.geometry.demo_pit import build_demo_stages
from geoai_simkit.core.types import RegionTag


class DummyGrid:
    def __init__(self, n_cells: int = 8):
        self.n_cells = n_cells
        self.celltypes = np.asarray([12] * n_cells, dtype=np.int32)

    def cast_to_unstructured_grid(self):
        return self


def _model() -> SimulationModel:
    model = SimulationModel(name='pit', mesh=DummyGrid())
    model.region_tags = [
        RegionTag('soil_mass', np.arange(0, 2, dtype=np.int64)),
        RegionTag('soil_excavation_1', np.arange(2, 4, dtype=np.int64)),
        RegionTag('soil_excavation_2', np.arange(4, 6, dtype=np.int64)),
        RegionTag('wall', np.arange(6, 8, dtype=np.int64)),
    ]
    model.metadata.update({
        'source': 'parametric_pit',
        'demo_wall_mode': 'plaxis_like_auto',
        'demo_enabled_support_groups': ['crown_beam', 'strut_level_1', 'strut_level_2'],
        'demo_enabled_interface_groups': ['outer', 'inner_upper', 'inner_lower'],
    })
    model.structures = [
        StructuralElementDefinition('crown', 'frame3d', (0, 1), active_stages=('initial', 'excavate_level_1', 'excavate_level_2'), metadata={'support_group': 'crown_beam'}),
        StructuralElementDefinition('strut1', 'truss2', (0, 1), active_stages=('excavate_level_1', 'excavate_level_2'), metadata={'support_group': 'strut_level_1'}),
        StructuralElementDefinition('strut2', 'truss2', (0, 1), active_stages=('excavate_level_2',), metadata={'support_group': 'strut_level_2'}),
    ]
    model.interfaces = [
        InterfaceDefinition('outer', 'node_pair', (0,), (1,), active_stages=(), metadata={'wall_contact_group': 'outer'}),
        InterfaceDefinition('upper', 'node_pair', (0,), (1,), active_stages=('initial',), metadata={'wall_contact_group': 'inner_upper'}),
        InterfaceDefinition('lower', 'node_pair', (0,), (1,), active_stages=('initial', 'excavate_level_1'), metadata={'wall_contact_group': 'inner_lower'}),
    ]
    model.stages = build_demo_stages(model, wall_active=True)
    return model


def test_demo_stages_expose_expected_active_support_groups() -> None:
    model = _model()
    assert model.stage_by_name('initial').metadata['active_support_groups'] == ['crown_beam']
    assert model.stage_by_name('excavate_level_1').metadata['active_support_groups'] == ['crown_beam', 'strut_level_1']
    assert model.stage_by_name('excavate_level_2').metadata['active_support_groups'] == ['crown_beam', 'strut_level_1', 'strut_level_2']


def test_model_structure_and_interface_filters_respect_stage_metadata() -> None:
    model = _model()
    assert {s.metadata['support_group'] for s in model.structures_for_stage('initial')} == {'crown_beam'}
    assert {s.metadata['support_group'] for s in model.structures_for_stage('excavate_level_1')} == {'crown_beam', 'strut_level_1'}
    assert {s.metadata['support_group'] for s in model.structures_for_stage('excavate_level_2')} == {'crown_beam', 'strut_level_1', 'strut_level_2'}
    assert {i.metadata['wall_contact_group'] for i in model.interfaces_for_stage('initial')} == {'outer', 'inner_upper', 'inner_lower'}
    assert {i.metadata['wall_contact_group'] for i in model.interfaces_for_stage('excavate_level_1')} == {'outer', 'inner_lower'}
    assert {i.metadata['wall_contact_group'] for i in model.interfaces_for_stage('excavate_level_2')} == {'outer'}
