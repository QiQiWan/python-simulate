from __future__ import annotations

import numpy as np
import pytest

sp = pytest.importorskip('scipy.sparse')

from geoai_simkit.solver.warp_hex8 import block_values_matvec, block_values_to_csr, build_block_sparse_pattern, build_node_block_sparse_pattern, pattern_slot_lookup


def test_block_sparse_pattern_and_finalize_to_csr() -> None:
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)
    pattern = build_block_sparse_pattern(elements)
    assert pattern.rows.shape == pattern.cols.shape
    assert pattern.elem_block_slots.shape == (1, 64)
    vals = np.zeros((pattern.rows.shape[0], 3, 3), dtype=float)
    vals[:, :, :] = np.eye(3)[None, :, :]
    K = block_values_to_csr(pattern, vals, ndof=24)
    assert sp.issparse(K)
    assert K.shape == (24, 24)
    assert K.nnz > 0


def test_node_block_sparse_pattern_merges_multiple_connectivities() -> None:
    pattern = build_node_block_sparse_pattern([
        np.array([[0, 1, 2]], dtype=np.int32),
        np.array([[2, 3]], dtype=np.int32),
    ], n_nodes=4)
    lookup = pattern_slot_lookup(pattern)
    assert lookup[(0, 1)] >= 0
    assert lookup[(2, 3)] >= 0
    assert pattern.diag_block_slots.shape == (4,)
    assert np.all(pattern.diag_block_slots >= 0)


def test_block_sparse_matvec_matches_csr_product() -> None:
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)
    pattern = build_block_sparse_pattern(elements)
    rng = np.random.default_rng(42)
    vals = rng.normal(size=(pattern.rows.shape[0], 3, 3))
    x = rng.normal(size=24)
    y_blk = block_values_matvec(pattern, vals, x, block_size=3, ndof=24)
    K = block_values_to_csr(pattern, vals, ndof=24)
    y_ref = np.asarray(K @ x, dtype=float)
    assert np.allclose(y_blk, y_ref)
