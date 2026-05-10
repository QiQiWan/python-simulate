from __future__ import annotations

import numpy as np


def solve_linear_system(K: np.ndarray, f: np.ndarray, fixed_dofs: dict[int, float] | None = None) -> np.ndarray:
    """Solve a dense linear system with displacement constraints.

    This intentionally keeps the benchmark path dependency-light. Production paths
    can replace it with CSR/BSR sparse solvers without changing benchmark contracts.
    """
    K = np.asarray(K, dtype=float)
    f = np.asarray(f, dtype=float).reshape(-1)
    n = f.size
    fixed = dict(fixed_dofs or {})
    u = np.zeros(n, dtype=float)
    if fixed:
        for dof, value in fixed.items():
            if 0 <= int(dof) < n:
                u[int(dof)] = float(value)
        free = np.array([i for i in range(n) if i not in fixed], dtype=int)
        if free.size == 0:
            return u
        Kff = K[np.ix_(free, free)]
        rhs = f[free] - K[np.ix_(free, np.array(list(fixed.keys()), dtype=int))] @ np.array(list(fixed.values()), dtype=float)
        try:
            u[free] = np.linalg.solve(Kff, rhs)
        except np.linalg.LinAlgError:
            u[free] = np.linalg.lstsq(Kff + np.eye(Kff.shape[0]) * 1e-12, rhs, rcond=None)[0]
        return u
    try:
        return np.linalg.solve(K, f)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(K + np.eye(K.shape[0]) * 1e-12, f, rcond=None)[0]


def constrained_residual_norm(K: np.ndarray, u: np.ndarray, f: np.ndarray, fixed_dofs: dict[int, float] | None = None) -> float:
    r = np.asarray(K, dtype=float) @ np.asarray(u, dtype=float).reshape(-1) - np.asarray(f, dtype=float).reshape(-1)
    fixed = set((fixed_dofs or {}).keys())
    free = [i for i in range(r.size) if i not in fixed]
    if not free:
        return 0.0
    return float(np.linalg.norm(r[np.array(free, dtype=int)]))
