from geoai_simkit.core.model import SimulationModel
import pytest

pytest.importorskip('pyvista')

from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.geometry.demo_pit import (
    apply_demo_solver_preset,
    build_demo_stages,
    configure_demo_coupling,
    demo_solver_preset_payload,
    normalize_solver_preset,
)


def _build_model():
    model = SimulationModel(name='pit-demo', mesh=ParametricPitScene().build())
    model.ensure_regions()
    return model


def test_demo_solver_preset_payload_is_coupling_sensitive():
    conservative = demo_solver_preset_payload('conservative', coupled=True)
    aggressive = demo_solver_preset_payload('aggressive', coupled=True)
    assert conservative['initial_increment'] < aggressive['initial_increment']
    assert conservative['max_cutbacks'] > aggressive['max_cutbacks']


def test_apply_demo_solver_preset_writes_metadata():
    meta = apply_demo_solver_preset({}, 'conservative', coupled=False)
    assert meta['solver_preset'] == 'conservative'
    assert meta['compute_profile'] == 'cpu-safe'
    assert meta['coupled_demo_stage'] is False


def test_build_demo_stages_uses_selected_solver_preset():
    model = _build_model()
    model.metadata['demo_solver_preset'] = 'conservative'
    wall_mode = configure_demo_coupling(model, prefer_wall_solver=True, auto_supports=True, interface_policy='manual_like_nearest_soil')
    stages = build_demo_stages(model, wall_active=(wall_mode in {'auto_interface', 'plaxis_like_auto'}))
    assert stages[0].metadata['solver_preset'] == 'conservative'
    assert stages[0].metadata['initial_increment'] <= 0.00625
    assert stages[1].metadata['max_cutbacks'] >= 8


def test_normalize_solver_preset_defaults_to_balanced():
    assert normalize_solver_preset('unknown') == 'balanced'
