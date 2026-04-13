from __future__ import annotations

import numpy as np

from geoai_simkit.solver.linear_algebra import _warp_solution_to_numpy, _warp_solver_iterations


class _FakeWarpArray:
    def __init__(self, arr):
        self._arr = np.asarray(arr)

    def numpy(self):
        return np.asarray(self._arr)


def test_warp_solution_to_numpy_flattens_mutated_solution_buffer():
    x = _FakeWarpArray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    out = _warp_solution_to_numpy(x, expected_size=6, block_size=3)
    assert out.shape == (6,)
    assert np.allclose(out, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


def test_warp_solver_iterations_accepts_host_or_device_like_results():
    assert _warp_solver_iterations((7, 1.0e-6, 1.0e-8)) == 7
    assert _warp_solver_iterations((_FakeWarpArray([11]), _FakeWarpArray([1.0]), _FakeWarpArray([1.0]))) == 11
