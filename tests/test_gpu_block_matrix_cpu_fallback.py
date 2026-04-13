from __future__ import annotations

import numpy as np
import pytest

sp = pytest.importorskip('scipy.sparse')

from geoai_simkit.solver.linear_algebra import solve_linear_system
from geoai_simkit.solver.warp_hex8 import BlockSparsePattern, WarpBlockSparseMatrix


def test_block_sparse_matrix_materializes_to_csr():
    pattern = BlockSparsePattern(
        rows=np.asarray([0, 1], dtype=np.int32),
        cols=np.asarray([0, 1], dtype=np.int32),
        elem_block_slots=np.zeros((0, 64), dtype=np.int32),
        diag_block_slots=np.asarray([0, 1], dtype=np.int32),
    )
    values = np.asarray([
        np.eye(3) * 2.0,
        np.eye(3) * 4.0,
    ], dtype=float)
    mat = WarpBlockSparseMatrix(pattern=pattern, ndof=6, values_host=values)
    csr = mat.to_csr()
    assert sp.issparse(csr)
    arr = csr.toarray()
    assert arr.shape == (6, 6)
    assert np.allclose(np.diag(arr), [2.0, 2.0, 2.0, 4.0, 4.0, 4.0])


def test_block_sparse_matrix_cpu_penalty_solve_respects_dirichlet():
    pattern = BlockSparsePattern(
        rows=np.asarray([0, 1], dtype=np.int32),
        cols=np.asarray([0, 1], dtype=np.int32),
        elem_block_slots=np.zeros((0, 64), dtype=np.int32),
        diag_block_slots=np.asarray([0, 1], dtype=np.int32),
    )
    values = np.asarray([
        np.eye(3) * 5.0,
        np.eye(3) * 2.0,
    ], dtype=float)
    mat = WarpBlockSparseMatrix(pattern=pattern, ndof=6, values_host=values)
    rhs = np.ones(6, dtype=float)
    x, info = solve_linear_system(
        mat,
        rhs,
        prefer_sparse=True,
        sparse_threshold=2,
        assume_symmetric=True,
        metadata={'ordering': 'rcm', 'preconditioner': 'block-jacobi'},
        block_size=3,
        fixed_dofs=np.asarray([0], dtype=np.int64),
        fixed_values=np.asarray([0.5], dtype=float),
    )
    assert info.used_sparse is True
    assert x.shape == (6,)
    assert abs(float(x[0]) - 0.5) < 1.0e-6
    assert np.allclose(x[1:3], 0.2)
    assert np.allclose(x[3:], 0.5)
