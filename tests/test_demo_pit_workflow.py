from __future__ import annotations

import numpy as np

from geoai_simkit.app.presolve import analyze_presolve_state
from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, InterfaceDefinition, SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.solver.staging import StageManager
from geoai_simkit.validation_rules import validate_bc_inputs, validate_load_inputs


class DummyGrid:
    def __init__(self, n_cells: int = 12):
        self.n_cells = n_cells
        self.celltypes = np.asarray([12] * n_cells, dtype=np.int32)

    def cast_to_unstructured_grid(self):
        return self



def _make_model() -> SimulationModel:
    model = SimulationModel(name='pit', mesh=DummyGrid())
    model.metadata.update({'source': 'parametric_pit', 'demo_wall_mode': 'display_only'})
    model.region_tags = [
        RegionTag('soil_mass', np.arange(0, 4, dtype=np.int64)),
        RegionTag('soil_excavation_1', np.arange(4, 8, dtype=np.int64)),
        RegionTag('soil_excavation_2', np.arange(8, 10, dtype=np.int64)),
        RegionTag('wall', np.arange(10, 12, dtype=np.int64)),
    ]
    for name in ('soil_mass', 'soil_excavation_1', 'soil_excavation_2'):
        model.add_material(name, 'mohr_coulomb', E=10e6, nu=0.3, cohesion=10000.0, friction_deg=28.0, dilation_deg=0.0, tensile_strength=0.0, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    return model



def test_stage_manager_tracks_two_level_excavation_sequence() -> None:
    model = _make_model()
    model.add_stage(AnalysisStage(name='initial', metadata={'activation_map': {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': False}}))
    model.add_stage(AnalysisStage(name='excavate_level_1', metadata={'activation_map': {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': True, 'wall': False}}))
    model.add_stage(AnalysisStage(name='excavate_level_2', metadata={'activation_map': {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': False, 'wall': False}}))

    contexts = StageManager(model).iter_stages()
    assert contexts[0].active_regions == {'soil_mass', 'soil_excavation_1', 'soil_excavation_2'}
    assert contexts[1].active_regions == {'soil_mass', 'soil_excavation_2'}
    assert contexts[2].active_regions == {'soil_mass'}



def test_presolve_blocks_excavation_stage_without_real_change() -> None:
    model = _make_model()
    activation = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': False}
    model.add_stage(AnalysisStage(name='initial', metadata={'activation_map': dict(activation), 'initial_increment': 0.05}))
    model.add_stage(AnalysisStage(name='excavate_level_1', metadata={'activation_map': dict(activation), 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is False
    joined = '\n'.join(report.messages)
    assert '没有激活/失活' in joined or '没有检测到实际失活' in joined



def test_presolve_blocks_display_only_wall_when_activated() -> None:
    model = _make_model()
    activation = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', activate_regions=tuple(activation.keys()), steps=1, metadata={'activation_map': activation, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is False
    assert any('display-only' in msg or '不能直接参与求解' in msg for msg in report.messages)


def test_presolve_allows_auto_interface_wall_when_expected_groups_exist() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'auto_interface'
    model.interfaces = [
        InterfaceDefinition('outer_a', 'node_pair', (1,), (2,), active_stages=(), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'outer'}),
        InterfaceDefinition('inner_upper_a', 'node_pair', (3,), (4,), active_stages=('initial',), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_upper'}),
        InterfaceDefinition('inner_lower_a', 'node_pair', (5,), (6,), active_stages=('initial', 'excavate_level_1'), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_lower'}),
    ]
    activation0 = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    activation1 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': True, 'wall': True}
    activation2 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': False, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', activate_regions=tuple(activation0.keys()), steps=1, metadata={'activation_map': activation0, 'initial_increment': 0.05}))
    model.add_stage(AnalysisStage(name='excavate_level_1', activate_regions=tuple(activation1.keys()), steps=1, metadata={'activation_map': activation1, 'initial_increment': 0.05}))
    model.add_stage(AnalysisStage(name='excavate_level_2', activate_regions=tuple(activation2.keys()), steps=1, metadata={'activation_map': activation2, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is True


def test_presolve_blocks_auto_interface_wall_when_outer_group_missing() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'auto_interface'
    model.interfaces = [
        InterfaceDefinition('inner_upper_a', 'node_pair', (3,), (4,), active_stages=('initial',), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_upper'}),
        InterfaceDefinition('inner_lower_a', 'node_pair', (5,), (6,), active_stages=('initial', 'excavate_level_1'), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_lower'}),
    ]
    activation = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', activate_regions=tuple(activation.keys()), steps=1, metadata={'activation_map': activation, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is False
    assert any('outer' in msg for msg in report.messages)



def test_validation_accepts_boundary_alias_and_force_alias() -> None:
    bc_issues = validate_bc_inputs('fix_bottom', 'displacement', 'bottom', (0, 1, 2), (0.0, 0.0, 0.0))
    assert not [item for item in bc_issues if item.level == 'error']

    load_issues = validate_load_inputs('surcharge', 'point_force', 'top', (0.0, 0.0, -1000.0))
    assert not [item for item in load_issues if item.level == 'error']


def test_presolve_respects_enabled_interface_group_subset() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'auto_interface'
    model.metadata['demo_enabled_interface_groups'] = ['outer']
    model.interfaces = [
        InterfaceDefinition('outer_a', 'node_pair', (1,), (2,), active_stages=(), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'outer'}),
    ]
    activation = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', activate_regions=tuple(activation.keys()), steps=1, metadata={'activation_map': activation, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is True


def test_presolve_respects_enabled_support_group_subset() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'plaxis_like_auto'
    model.metadata['demo_enabled_interface_groups'] = ['outer']
    model.metadata['demo_enabled_support_groups'] = ['crown_beam', 'strut_level_1']
    model.interfaces = [
        InterfaceDefinition('outer_a', 'node_pair', (1,), (2,), active_stages=(), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'outer'}),
    ]
    from geoai_simkit.core.model import StructuralElementDefinition
    model.structures = [
        StructuralElementDefinition('crown_1', 'frame3d', (0, 1), active_stages=('initial', 'excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'crown_beam'}),
        StructuralElementDefinition('strut_1', 'truss2', (2, 3), active_stages=('excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'strut_level_1'}),
    ]
    activation0 = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    activation1 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': True, 'wall': True}
    activation2 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': False, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', activate_regions=tuple(activation0.keys()), steps=1, metadata={'activation_map': activation0, 'initial_increment': 0.05}))
    model.add_stage(AnalysisStage(name='excavate_level_1', activate_regions=tuple(activation1.keys()), steps=1, metadata={'activation_map': activation1, 'initial_increment': 0.05}))
    model.add_stage(AnalysisStage(name='excavate_level_2', activate_regions=tuple(activation2.keys()), steps=1, metadata={'activation_map': activation2, 'initial_increment': 0.05}))

    report = analyze_presolve_state(model)
    assert report.ok is True
