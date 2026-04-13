from __future__ import annotations

import numpy as np

from geoai_simkit.solver.linear_algebra import solve_linear_system


def test_dense_linear_solver_basic():
    A = np.array([[4.0, 1.0], [1.0, 3.0]], dtype=float)
    b = np.array([1.0, 2.0], dtype=float)
    x, info = solve_linear_system(A, b, prefer_sparse=False)
    assert info.backend in {"numpy-dense", "numpy-lstsq"}
    assert np.allclose(A @ x, b, atol=1e-8)


def test_dense_linear_solver_regularizes_singular():
    A = np.array([[1.0, 1.0], [1.0, 1.0]], dtype=float)
    b = np.array([1.0, 1.0], dtype=float)
    x, info = solve_linear_system(A, b, prefer_sparse=False)
    assert x.shape == (2,)
    assert np.all(np.isfinite(x))
    assert info.regularization > 0.0
