import pytest
pytest.importorskip('pyvista')
from geoai_simkit.solver.warp_backend import WarpBackend


def test_choose_stage_device_respects_stage_compute_profile_cpu_safe():
    device, note = WarpBackend._choose_stage_device('cuda:0', {'compute_profile': 'cpu-safe'}, active_cells=2500, active_dofs=12000)
    assert device == 'cpu'
    assert note is not None
