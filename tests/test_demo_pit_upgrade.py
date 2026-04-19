from __future__ import annotations

import numpy as np
import pytest

from geoai_simkit.app.presolve import analyze_presolve_state
from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, GeometryObjectRecord, InterfaceDefinition, SimulationModel, StructuralElementDefinition
from geoai_simkit.core.types import RegionTag
from geoai_simkit.geometry.demo_pit import build_demo_stages, expected_support_groups_for_stage


class DummyGrid:
    def __init__(self, n_cells: int = 12):
        self.n_cells = n_cells
        self.celltypes = np.asarray([12] * n_cells, dtype=np.int32)

    def cast_to_unstructured_grid(self):
        return self


def _make_model() -> SimulationModel:
    model = SimulationModel(name='pit', mesh=DummyGrid())
    model.metadata.update({'source': 'parametric_pit', 'demo_wall_mode': 'plaxis_like_auto'})
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


def _add_wall_ifaces(model: SimulationModel) -> None:
    model.interfaces = [
        InterfaceDefinition('outer_a', 'node_pair', (1,), (2,), active_stages=(), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'outer'}),
        InterfaceDefinition('inner_upper_a', 'node_pair', (3,), (4,), active_stages=('wall_activation',), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_upper'}),
        InterfaceDefinition('inner_lower_a', 'node_pair', (5,), (6,), active_stages=('wall_activation', 'excavate_level_1'), metadata={'source': 'parametric_pit_auto_wall', 'wall_contact_group': 'inner_lower'}),
    ]


def _add_supports(model: SimulationModel) -> None:
    model.structures = [
        StructuralElementDefinition('crown_1', 'frame3d', (0, 1), active_stages=('wall_activation', 'excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'crown_beam'}),
        StructuralElementDefinition('strut_1', 'truss2', (2, 3), active_stages=('excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'strut_level_1'}),
        StructuralElementDefinition('strut_2', 'truss2', (4, 5), active_stages=('excavate_level_2',), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'strut_level_2'}),
    ]


def test_object_record_for_key_alias_works() -> None:
    model = SimulationModel(name='demo', mesh=DummyGrid())
    model.object_records = [GeometryObjectRecord(key='retaining_wall', name='retaining_wall', object_type='RetainingWall')]
    assert model.object_record_for_key('retaining_wall') is not None


def test_expected_support_groups_follow_excavation_sequence() -> None:
    assert expected_support_groups_for_stage('initial') == set()
    assert expected_support_groups_for_stage('wall_activation') == {'crown_beam'}
    assert expected_support_groups_for_stage('excavate_level_1') == {'crown_beam', 'strut_level_1'}
    assert expected_support_groups_for_stage('excavate_level_2') == {'crown_beam', 'strut_level_1', 'strut_level_2'}


def test_presolve_allows_plaxis_like_auto_when_support_groups_exist() -> None:
    model = _make_model()
    _add_wall_ifaces(model)
    _add_supports(model)
    activation0 = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': False}
    activation_wall = {'soil_mass': True, 'soil_excavation_1': True, 'soil_excavation_2': True, 'wall': True}
    activation1 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': True, 'wall': True}
    activation2 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': False, 'wall': True}
    model.add_stage(AnalysisStage(name='initial', metadata={'activation_map': activation0, 'initial_increment': 0.05}, steps=1))
    model.add_stage(AnalysisStage(name='wall_activation', metadata={'activation_map': activation_wall, 'initial_increment': 0.025}, steps=1))
    model.add_stage(AnalysisStage(name='excavate_level_1', metadata={'activation_map': activation1, 'initial_increment': 0.05}, steps=1))
    model.add_stage(AnalysisStage(name='excavate_level_2', metadata={'activation_map': activation2, 'initial_increment': 0.05}, steps=1))

    report = analyze_presolve_state(model)
    assert report.ok is True


def test_presolve_blocks_plaxis_like_auto_when_support_group_missing() -> None:
    model = _make_model()
    _add_wall_ifaces(model)
    model.structures = [
        StructuralElementDefinition('crown_1', 'frame3d', (0, 1), active_stages=('wall_activation', 'excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'crown_beam'}),
        StructuralElementDefinition('strut_1', 'truss2', (2, 3), active_stages=('excavate_level_1', 'excavate_level_2'), metadata={'source': 'parametric_pit_auto_support', 'support_group': 'strut_level_1'}),
    ]
    activation2 = {'soil_mass': True, 'soil_excavation_1': False, 'soil_excavation_2': False, 'wall': True}
    model.add_stage(AnalysisStage(name='excavate_level_2', metadata={'activation_map': activation2, 'initial_increment': 0.05}, steps=1))

    report = analyze_presolve_state(model)
    assert report.ok is False
    assert any('strut_level_2' in msg for msg in report.messages)


def test_demo_coupling_creates_interfaces_and_supports_for_real_scene() -> None:
    pytest.importorskip('pyvista')
    from geoai_simkit.geometry.demo_pit import build_demo_support_structures, configure_demo_coupling, summarize_demo_coupling
    from geoai_simkit.geometry.parametric import ParametricPitScene

    scene = ParametricPitScene(length=24.0, width=12.0, depth=12.0, soil_depth=20.0, nx=8, ny=6, nz=6, wall_thickness=0.6)
    model = SimulationModel(name='pit', mesh=scene.build())
    model.metadata.update({
        'source': 'parametric_pit',
        'parametric_scene': {
            'length': scene.length,
            'width': scene.width,
            'depth': scene.depth,
            'soil_depth': scene.soil_depth,
            'wall_thickness': scene.wall_thickness,
        },
    })
    model.ensure_regions()
    mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=True)
    summary = summarize_demo_coupling(model)
    assert mode in {'auto_interface', 'plaxis_like_auto'}
    assert summary.interface_count > 0
    assert summary.structure_count > 0
    assert build_demo_support_structures(model)


def test_build_demo_stages_uses_more_conservative_defaults_for_coupled_wall_mode() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'plaxis_like_auto'
    stages = build_demo_stages(model, wall_active=True)
    assert [stage.name for stage in stages] == ['initial', 'wall_activation', 'excavate_level_1', 'excavate_level_2']
    assert stages[0].steps == 6
    assert stages[1].steps == 6
    assert stages[2].steps == 8
    assert float(stages[0].metadata['initial_increment']) == 0.0125
    assert stages[0].metadata['initial_state_strategy'] == 'geostatic_seeded_linear'
    assert int(stages[1].metadata['max_iterations']) >= 44
    assert float(stages[1].metadata['initial_increment']) <= 0.00625
    assert int(stages[1].metadata['modified_newton_max_reuse']) == 0


def test_build_demo_stages_preserves_region_override_metadata() -> None:
    model = _make_model()
    model.metadata['demo_wall_mode'] = 'auto_interface'
    model.metadata['demo_interface_region_overrides'] = {'outer': 'soil_mass', 'inner_lower': 'soil_excavation_2'}
    stages = build_demo_stages(model, wall_active=True)
    assert stages[0].metadata['interface_region_overrides'] == {'outer': 'soil_mass', 'inner_lower': 'soil_excavation_2'}


def test_select_bc_nodes_accepts_boundary_aliases_without_nameerror() -> None:
    from geoai_simkit.solver.hex8_linear import select_bc_nodes

    points = np.asarray([
        [0.0, 0.0, -2.0],
        [1.0, 0.0, -2.0],
        [0.0, 0.0, 0.0],
    ], dtype=float)
    bc = BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0))
    node_ids = select_bc_nodes(points, bc)
    assert node_ids.tolist() == [0, 1]
