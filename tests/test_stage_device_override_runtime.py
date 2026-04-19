import pytest

pytest.importorskip('pyvista')

from geoai_simkit.solver.warp_backend import WarpBackend


def test_choose_stage_device_respects_stage_cpu_safe_metadata():
    device, note = WarpBackend._choose_stage_device(
        'cuda:0',
        {'compute_profile': 'cpu-safe', 'adaptive_small_model_cpu': False},
        active_cells=5000,
        active_dofs=15000,
    )
    assert device == 'cpu'
    assert 'cpu-safe' in (note or '').lower()
