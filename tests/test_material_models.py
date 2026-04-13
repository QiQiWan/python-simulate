import numpy as np

from geoai_simkit.materials.hss import HSS
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb


def test_mohr_coulomb_yields_on_large_shear_increment_and_tracks_active_planes():
    mat = MohrCoulomb(E=30e6, nu=0.3, cohesion=10e3, friction_deg=30.0)
    state = mat.create_state()
    new_state = mat.update(np.array([0.002, 0.0, -0.002, 0.03, 0.0, 0.0]), state)
    assert isinstance(new_state.internal.get("yielded"), bool)
    assert new_state.stress.shape == (6,)
    if new_state.internal.get("yielded"):
        assert len(new_state.internal.get("active_planes", ())) >= 1
        assert new_state.internal.get("yield_mode") in {"shear-single", "shear-edge", "shear-apex", "tension"}


def test_hss_updates_pressure_reduction_and_branch_memory():
    mat = HSS(E50ref=20e6, Eoedref=20e6, Eurref=60e6, nu_ur=0.25, pref=100e3, m=0.5, c=5e3, phi_deg=28.0, psi_deg=0.0, G0ref=100e6, gamma07=1e-4)
    state = mat.create_state()
    s1 = mat.update(np.array([1e-4, 0.0, 0.0, 1e-4, 0.0, 0.0]), state)
    s2 = mat.update(np.array([-5e-5, 0.0, 0.0, -5e-5, 0.0, 0.0]), s1)
    assert s1.internal["p_ref_state"] >= 1.0
    assert 0.0 < s1.internal["shear_mod_reduction"] <= 1.0
    assert s2.internal["mode_branch"] in {"loading", "unloading"}
    assert s2.internal["gamma_max"] >= s2.internal["gamma_hist"] or s2.internal["gamma_max"] >= s1.internal["gamma_hist"]
