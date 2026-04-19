from __future__ import annotations

import importlib
import sys
import types

import numpy as np

from geoai_simkit.materials.linear_elastic import LinearElastic
from geoai_simkit.materials import MaterialState


def _import_backend_without_real_pyvista():
    existing = sys.modules.get('pyvista')
    if existing is None:
        pv = types.ModuleType('pyvista')
        pv.DataSet = type('DataSet', (), {})
        pv.MultiBlock = type('MultiBlock', (), {})
        pv.UnstructuredGrid = type('UnstructuredGrid', (), {})
        sys.modules['pyvista'] = pv
    try:
        module = importlib.import_module('geoai_simkit.solver.warp_backend')
        return module.WarpBackend
    finally:
        if existing is None:
            sys.modules.pop('pyvista', None)
            sys.modules.pop('geoai_simkit.geometry.mesh_adapter', None)
            sys.modules.pop('geoai_simkit.solver.warp_backend', None)


def test_seed_states_from_cell_stress_builds_restartable_gp_states() -> None:
    WarpBackend = _import_backend_without_real_pyvista()
    backend = WarpBackend()
    mats = [LinearElastic(E=2.0e7, nu=0.30, rho=1800.0)]
    previous = [[MaterialState(
        stress=np.zeros(6, dtype=float),
        strain=np.zeros(6, dtype=float),
        plastic_strain=np.zeros(6, dtype=float),
        internal={'tag': 'restart'},
    ) for _ in range(8)]]
    cell_stress = np.array([[1200.0, 1100.0, 2500.0, 50.0, 25.0, 10.0]], dtype=float)

    seeded = backend._seed_states_from_cell_stress(mats, cell_stress, previous_states=previous)

    assert len(seeded) == 1
    assert len(seeded[0]) == 8
    for gp_state in seeded[0]:
        assert np.allclose(gp_state.stress, cell_stress[0])
        assert np.isfinite(gp_state.strain).all()
        assert gp_state.internal.get('tag') == 'restart'


def test_solver_mode_classification_reports_hybrid_when_linearized_and_nonlinear_stages_mix() -> None:
    WarpBackend = _import_backend_without_real_pyvista()
    backend = WarpBackend()

    assert backend._classify_hex8_solver_mode(
        nonlinear_present=True,
        nonlinear_stage_count=2,
        linearized_stage_count=1,
    ) == 'hybrid-staged-hex8'
    assert backend._classify_hex8_solver_mode(
        nonlinear_present=True,
        nonlinear_stage_count=0,
        linearized_stage_count=3,
    ) == 'staged-linearized-hex8'
    assert backend._classify_hex8_solver_mode(
        nonlinear_present=True,
        nonlinear_stage_count=3,
        linearized_stage_count=0,
    ) == 'nonlinear-hex8'
