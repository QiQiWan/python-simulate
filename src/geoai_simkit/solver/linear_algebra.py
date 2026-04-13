from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import os
from typing import Any

import numpy as np


@dataclass(slots=True)
class LinearSolveInfo:
    backend: str
    regularization: float
    used_sparse: bool = False
    iterations: int = 1
    warnings: list[str] = field(default_factory=list)
    thread_count: int = 0



def configure_linear_algebra_threads(thread_count: int) -> int:
    try:
        tc = int(thread_count)
    except Exception:
        tc = 0
    if tc <= 0:
        return 0
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = str(tc)
    return tc

def _optional_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def solve_linear_system(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    prefer_sparse: bool = True,
    sparse_threshold: int = 400,
    regularization_floor: float = 1.0e-9,
    regularization_scale: float = 1.0e-10,
    thread_count: int = 0,
) -> tuple[np.ndarray, LinearSolveInfo]:
    tc = configure_linear_algebra_threads(thread_count)
    A = np.asarray(matrix, dtype=float)
    b = np.asarray(rhs, dtype=float)
    if A.size == 0:
        return np.empty((0,), dtype=float), LinearSolveInfo(backend='empty', regularization=0.0, thread_count=tc)
    diag = np.abs(np.diag(A)) if A.ndim == 2 and A.shape[0] else np.array([1.0])
    reg = max(regularization_floor, regularization_scale * float(np.max(diag)))
    n = int(A.shape[0])
    warnings: list[str] = []

    if prefer_sparse and n >= sparse_threshold:
        sp = _optional_import('scipy.sparse')
        spla = _optional_import('scipy.sparse.linalg')
        if sp is not None and spla is not None:
            try:
                Asp = sp.csr_matrix(A)
                Asp = Asp + sp.eye(n, format='csr') * reg
                x = np.asarray(spla.spsolve(Asp, b), dtype=float)
                if not np.all(np.isfinite(x)):
                    raise RuntimeError('spsolve produced non-finite values')
                return x, LinearSolveInfo(backend='scipy-sparse', regularization=reg, used_sparse=True, warnings=warnings, thread_count=tc)
            except Exception as exc:  # pragma: no cover - sparse path optional / platform dependent
                warnings.append(f'sparse solver fallback: {exc}')

    Areg = A + np.eye(n, dtype=float) * reg
    try:
        x = np.linalg.solve(Areg, b)
        return np.asarray(x, dtype=float), LinearSolveInfo(backend='numpy-dense', regularization=reg, used_sparse=False, warnings=warnings, thread_count=tc)
    except np.linalg.LinAlgError:
        warnings.append('dense solve singular; using least-squares fallback')
        x, *_ = np.linalg.lstsq(Areg, b, rcond=None)
        return np.asarray(x, dtype=float), LinearSolveInfo(backend='numpy-lstsq', regularization=reg, used_sparse=False, warnings=warnings, thread_count=tc)
