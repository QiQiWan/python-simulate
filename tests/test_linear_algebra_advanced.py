from __future__ import annotations

import numpy as np
import pytest

sp = pytest.importorskip('scipy.sparse')

from geoai_simkit.solver.linear_algebra import LinearSolverContext, solve_linear_system


def test_sparse_solver_reports_strategy_details():
    A = sp.diags([np.full(40, 4.0), np.full(39, -1.0), np.full(39, -1.0)], [0, -1, 1], format='csr')
    b = np.ones(40, dtype=float)
    x, info = solve_linear_system(
        A,
        b,
        prefer_sparse=True,
        sparse_threshold=8,
        assume_symmetric=True,
        metadata={'ordering': 'rcm', 'preconditioner': 'block-jacobi', 'block_size': 2},
        block_size=2,
    )
    assert x.shape == (40,)
    assert info.used_sparse is True
    assert info.symmetric is True
    assert info.ordering == 'rcm'
    assert info.preconditioner == 'block-jacobi'
    assert np.all(np.isfinite(x))


def test_sparse_solver_context_reuses_pattern_and_preconditioner():
    A = sp.diags([np.full(24, 3.0), np.full(23, -1.0), np.full(23, -1.0)], [0, -1, 1], format='csr')
    b = np.ones(24, dtype=float)
    ctx = LinearSolverContext()
    solve_linear_system(
        A,
        b,
        prefer_sparse=True,
        sparse_threshold=8,
        assume_symmetric=True,
        context=ctx,
        metadata={'ordering': 'rcm', 'preconditioner': 'block-jacobi', 'block_size': 3},
        block_size=3,
    )
    _, info2 = solve_linear_system(
        A,
        b,
        prefer_sparse=True,
        sparse_threshold=8,
        assume_symmetric=True,
        context=ctx,
        metadata={'ordering': 'rcm', 'preconditioner': 'block-jacobi', 'block_size': 3},
        block_size=3,
    )
    assert info2.reused_pattern is True
    assert info2.reused_factorization is True
