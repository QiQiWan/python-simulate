from __future__ import annotations

from geoai_simkit.solver.linear_algebra import solve_linear_system


def solve_iterative(matrix, rhs, *, context=None, **kwargs):
    return solve_linear_system(matrix, rhs, context=context, **kwargs)
