import numpy as np

from geoai_simkit.solver.warp_hex8 import WarpHex8Config, try_warp_hex8_linear_assembly
from geoai_simkit.solver import warp_hex8, warp_nonlinear
from geoai_simkit.solver.warp_nonlinear import try_warp_nonlinear_continuum_assembly


def test_warp_nonlinear_bundle_failure_falls_back(monkeypatch):
    monkeypatch.setattr(warp_nonlinear, '_detect_material_family', lambda materials, cfg: ('hss', []))
    monkeypatch.setattr(warp_nonlinear, '_get_warp_nonlinear_bundle', lambda: (_ for _ in ()).throw(NameError('vec6f is not defined')))
    monkeypatch.setattr(warp_nonlinear, '_WARP_NONLINEAR_FAILURES', {})

    points = np.zeros((8, 3), dtype=float)
    elements = np.zeros((1, 8), dtype=np.int32)
    du = np.zeros(points.shape[0] * 3, dtype=float)

    K, fint, states, cell_stress, cell_yield, cell_eqp, info = try_warp_nonlinear_continuum_assembly(
        points=points,
        elements=elements,
        materials=[],
        du_step_trans=du,
        base_states=[],
        total_ndof=du.size,
        assemble_tangent=True,
        requested_device='cuda',
        solver_metadata={'warp_nonlinear_enabled': True, 'warp_nonlinear_force': True, 'warp_nonlinear_min_cells': 1},
        block_pattern=None,
    )

    assert K is None
    assert fint is None
    assert states is None
    assert cell_stress is None
    assert cell_yield is None
    assert cell_eqp is None
    assert info.used is False
    assert any('failed to build Warp nonlinear kernels' in w for w in info.warnings)
    assert 'cuda:0' in warp_nonlinear._WARP_NONLINEAR_FAILURES


def test_warp_hex8_bundle_failure_falls_back(monkeypatch):
    monkeypatch.setattr(warp_hex8, '_get_warp_kernel_bundle', lambda: (_ for _ in ()).throw(NameError('vec6f is not defined')))
    monkeypatch.setattr(warp_hex8, '_WARP_HEX8_FAILURES', {})

    points = np.zeros((8, 3), dtype=float)
    elements = np.zeros((1, 8), dtype=np.int32)
    young = np.ones(1, dtype=float)
    nu = np.full(1, 0.25, dtype=float)
    rho = np.zeros(1, dtype=float)

    K, f, info = try_warp_hex8_linear_assembly(
        points,
        elements,
        young,
        nu,
        rho,
        (0.0, 0.0, -9.81),
        ndof=24,
        requested_device='cuda',
        config=WarpHex8Config(enabled=True, force=True, min_cells=1),
        block_pattern=None,
    )

    assert K is None
    assert f is None
    assert info.used is False
    assert any('failed to build Warp hex8 kernels' in w for w in info.warnings)
    assert 'cuda:0' in warp_hex8._WARP_HEX8_FAILURES
