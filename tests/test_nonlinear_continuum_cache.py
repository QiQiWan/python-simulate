from __future__ import annotations

import numpy as np

from geoai_simkit.core.model import BoundaryCondition
from geoai_simkit.materials.linear_elastic import LinearElastic
from geoai_simkit.solver.hex8_linear import Hex8Submesh
from geoai_simkit.solver.hex8_nonlinear import NonlinearHex8Solver


def _unit_hex_submesh() -> Hex8Submesh:
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ], dtype=float)
    elems = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    gids = np.arange(8, dtype=np.int64)
    return Hex8Submesh(
        global_point_ids=gids,
        points=pts,
        elements=elems,
        full_cell_ids=np.array([0], dtype=np.int64),
        local_by_global={int(i): int(i) for i in gids},
    )


def test_nonlinear_solver_caches_linear_elastic_continuum_tangent() -> None:
    submesh = _unit_hex_submesh()
    solver = NonlinearHex8Solver(submesh, [LinearElastic(E=5.0e6, nu=0.3, rho=1800.0)], gravity=(0.0, 0.0, -9.81))
    result = solver.solve(
        bcs=(BoundaryCondition(name='fix_bottom', kind='displacement', target='zmin', components=(0, 1, 2), values=(0.0, 0.0, 0.0)),),
        loads=(),
        n_steps=1,
        max_iterations=6,
        tolerance=1.0e-8,
        prefer_sparse=True,
        line_search=False,
        compute_device='cpu',
        solver_metadata={'ordering': 'rcm', 'preconditioner': 'block-jacobi'},
    )
    assert solver._constant_continuum_K is not None
    assert any('cached tangent backend' in msg for msg in result.warnings)
    assert np.all(np.isfinite(result.u_nodes))
    assert result.cell_stress.shape == (1, 6)
