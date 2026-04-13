from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
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
    ordering: str = "natural"
    preconditioner: str = "none"
    symmetric: bool = False
    reused_pattern: bool = False
    reused_factorization: bool = False
    block_size: int = 1
    device: str = "cpu"


@dataclass(slots=True)
class LinearSolverContext:
    pattern_signature: str | None = None
    ordering: str = "natural"
    permutation: np.ndarray | None = None
    inverse_permutation: np.ndarray | None = None
    preconditioner_key: tuple[Any, ...] | None = None
    preconditioner_operator: Any | None = None
    factorization_key: tuple[Any, ...] | None = None
    factorization: Any | None = None
    matrix_hash: str | None = None
    solve_count: int = 0


def default_thread_count() -> int:
    total = int(os.cpu_count() or 1)
    return max(1, total - 1)



def configure_linear_algebra_threads(thread_count: int) -> int:
    try:
        tc = int(thread_count)
    except Exception:
        tc = 0
    if tc <= 0:
        tc = default_thread_count()
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = str(tc)
    return tc


def _optional_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _is_custom_block_sparse_matrix(matrix: Any) -> bool:
    return bool(hasattr(matrix, 'pattern') and hasattr(matrix, 'to_csr') and hasattr(matrix, 'block_size'))


def _materialize_custom_block_sparse(matrix: Any) -> Any:
    if _is_custom_block_sparse_matrix(matrix):
        return matrix.to_csr()
    return matrix


def _matrix_data_hash(matrix: Any) -> str:
    matrix = _materialize_custom_block_sparse(matrix)
    sp = _optional_import('scipy.sparse')
    if sp is not None and getattr(sp, 'issparse', lambda *_: False)(matrix):
        A = matrix.tocsr()
        digest = hashlib.sha1()
        digest.update(np.asarray(A.data, dtype=np.float64).tobytes())
        digest.update(np.asarray(A.indices, dtype=np.int64).tobytes())
        digest.update(np.asarray(A.indptr, dtype=np.int64).tobytes())
        digest.update(np.asarray(A.shape, dtype=np.int64).tobytes())
        return digest.hexdigest()
    A = np.asarray(matrix, dtype=np.float64)
    digest = hashlib.sha1()
    digest.update(A.tobytes())
    digest.update(np.asarray(A.shape, dtype=np.int64).tobytes())
    return digest.hexdigest()



def _matrix_pattern_signature(matrix: Any) -> str:
    matrix = _materialize_custom_block_sparse(matrix)
    sp = _optional_import('scipy.sparse')
    if sp is not None and getattr(sp, 'issparse', lambda *_: False)(matrix):
        A = matrix.tocsr()
        digest = hashlib.sha1()
        digest.update(np.asarray(A.indices, dtype=np.int64).tobytes())
        digest.update(np.asarray(A.indptr, dtype=np.int64).tobytes())
        digest.update(np.asarray(A.shape, dtype=np.int64).tobytes())
        return digest.hexdigest()
    A = np.asarray(matrix)
    mask = np.asarray(np.abs(A) > 0.0, dtype=np.uint8)
    digest = hashlib.sha1()
    digest.update(mask.tobytes())
    digest.update(np.asarray(A.shape, dtype=np.int64).tobytes())
    return digest.hexdigest()



def _is_probably_symmetric(matrix: Any, tol: float = 1.0e-9) -> bool:
    matrix = _materialize_custom_block_sparse(matrix)
    sp = _optional_import('scipy.sparse')
    if sp is not None and getattr(sp, 'issparse', lambda *_: False)(matrix):
        A = matrix.tocsr()
        if A.shape[0] != A.shape[1]:
            return False
        diff = A - A.T
        if diff.nnz == 0:
            return True
        if diff.nnz > max(100_000, 4 * A.shape[0]):
            sample = np.asarray(diff.data[: min(diff.nnz, 4096)], dtype=float)
            return bool(sample.size == 0 or np.max(np.abs(sample)) <= tol)
        return float(np.max(np.abs(diff.data))) <= tol
    A = np.asarray(matrix, dtype=float)
    return bool(A.ndim == 2 and A.shape[0] == A.shape[1] and np.allclose(A, A.T, atol=tol, rtol=tol))



def _choose_ordering(metadata: dict[str, Any] | None, symmetric: bool) -> str:
    meta = metadata or {}
    ordering = str(meta.get('ordering', 'auto')).lower()
    if ordering == 'auto':
        return 'rcm' if symmetric else 'colamd'
    if ordering in {'natural', 'none'}:
        return 'natural'
    if ordering in {'rcm', 'amd', 'colamd', 'mmd_ata', 'mmd_at_plus_a'}:
        return ordering
    return 'natural'



def _compute_permutation(matrix: Any, ordering: str, symmetric: bool, context: LinearSolverContext | None = None) -> tuple[np.ndarray | None, np.ndarray | None, bool, list[str]]:
    warnings: list[str] = []
    if ordering == 'natural':
        return None, None, False, warnings
    sp = _optional_import('scipy.sparse')
    csgraph = _optional_import('scipy.sparse.csgraph')
    if sp is None or csgraph is None or not getattr(sp, 'issparse', lambda *_: False)(matrix):
        warnings.append('reordering requested but scipy sparse graph tools are unavailable')
        return None, None, False, warnings
    pattern_sig = _matrix_pattern_signature(matrix)
    if context is not None and context.pattern_signature == pattern_sig and context.ordering == ordering and context.permutation is not None and context.inverse_permutation is not None:
        return context.permutation, context.inverse_permutation, True, warnings
    A = matrix.tocsr()
    perm: np.ndarray | None = None
    if ordering == 'rcm':
        perm = np.asarray(csgraph.reverse_cuthill_mckee(A if not symmetric else (A + A.T).tocsr(), symmetric_mode=bool(symmetric)), dtype=np.int64)
    elif ordering in {'amd', 'colamd', 'mmd_ata', 'mmd_at_plus_a'}:
        # Iterative paths do not expose AMD directly in SciPy. Reuse an RCM permutation for the Krylov solve,
        # while direct factorization will still use the requested SuperLU permutation spec later on.
        perm = np.asarray(csgraph.reverse_cuthill_mckee(A if not symmetric else (A + A.T).tocsr(), symmetric_mode=bool(symmetric)), dtype=np.int64)
    if perm is None or perm.size == 0:
        return None, None, False, warnings
    inv = np.empty_like(perm)
    inv[perm] = np.arange(perm.size, dtype=np.int64)
    if context is not None:
        context.pattern_signature = pattern_sig
        context.ordering = ordering
        context.permutation = perm
        context.inverse_permutation = inv
    return perm, inv, False, warnings



def _apply_permutation(matrix: Any, rhs: np.ndarray, perm: np.ndarray | None) -> tuple[Any, np.ndarray]:
    if perm is None:
        return matrix, rhs
    sp = _optional_import('scipy.sparse')
    if sp is not None and getattr(sp, 'issparse', lambda *_: False)(matrix):
        A = matrix.tocsr()[perm][:, perm]
    else:
        A = np.asarray(matrix, dtype=float)[np.ix_(perm, perm)]
    return A, np.asarray(rhs, dtype=float)[perm]



def _restore_permutation(x: np.ndarray, inv_perm: np.ndarray | None) -> np.ndarray:
    if inv_perm is None:
        return np.asarray(x, dtype=float)
    out = np.empty_like(np.asarray(x, dtype=float))
    out[inv_perm] = np.asarray(x, dtype=float)
    return out



def _build_block_jacobi_preconditioner(A: Any, block_size: int, reg: float, context: LinearSolverContext | None) -> tuple[Any | None, bool, list[str]]:
    warnings: list[str] = []
    sp = _optional_import('scipy.sparse')
    spla = _optional_import('scipy.sparse.linalg')
    if sp is None or spla is None or not getattr(sp, 'issparse', lambda *_: False)(A):
        warnings.append('block-jacobi requires scipy sparse support')
        return None, False, warnings
    n = int(A.shape[0])
    bs = max(1, int(block_size))
    key = ('block-jacobi', _matrix_pattern_signature(A), bs)
    if context is not None and context.preconditioner_key == key and context.preconditioner_operator is not None:
        return context.preconditioner_operator, True, warnings
    A_csr = A.tocsr()
    inv_blocks: list[np.ndarray] = []
    for start in range(0, n, bs):
        stop = min(n, start + bs)
        block = np.asarray(A_csr[start:stop, start:stop].toarray(), dtype=float)
        if block.size == 0:
            inv_blocks.append(np.zeros((stop - start, stop - start), dtype=float))
            continue
        block = block + np.eye(block.shape[0], dtype=float) * reg
        try:
            inv_blocks.append(np.linalg.inv(block))
        except np.linalg.LinAlgError:
            inv_blocks.append(np.linalg.pinv(block))
            warnings.append(f'block-jacobi used pseudo-inverse for block [{start}:{stop}]')

    def _matvec(x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        y = np.zeros_like(x)
        for idx, start in enumerate(range(0, n, bs)):
            stop = min(n, start + bs)
            y[start:stop] = inv_blocks[idx] @ x[start:stop]
        return y

    M = spla.LinearOperator(A_csr.shape, matvec=_matvec, dtype=float)
    if context is not None:
        context.preconditioner_key = key
        context.preconditioner_operator = M
    return M, False, warnings



def _build_spilu_preconditioner(A: Any, metadata: dict[str, Any] | None, context: LinearSolverContext | None) -> tuple[Any | None, bool, list[str]]:
    warnings: list[str] = []
    sp = _optional_import('scipy.sparse')
    spla = _optional_import('scipy.sparse.linalg')
    if sp is None or spla is None or not getattr(sp, 'issparse', lambda *_: False)(A):
        warnings.append('spilu preconditioner requires scipy sparse support')
        return None, False, warnings
    meta = metadata or {}
    drop_tol = float(meta.get('spilu_drop_tol', 1.0e-3))
    fill_factor = float(meta.get('spilu_fill_factor', 8.0))
    key = ('spilu', _matrix_pattern_signature(A), drop_tol, fill_factor)
    if context is not None and context.preconditioner_key == key and context.preconditioner_operator is not None:
        return context.preconditioner_operator, True, warnings
    try:
        ilu = spla.spilu(A.tocsc(), drop_tol=drop_tol, fill_factor=fill_factor)
        M = spla.LinearOperator(A.shape, matvec=ilu.solve, dtype=float)
        if context is not None:
            context.preconditioner_key = key
            context.preconditioner_operator = M
        return M, False, warnings
    except Exception as exc:
        warnings.append(f'spilu preconditioner failed: {exc}')
        return None, False, warnings



def _warp_block_type(wp: Any, block_size: int) -> Any:
    if block_size == 1:
        return wp.float32
    if block_size == 2:
        return getattr(wp, 'mat22')
    if block_size == 3:
        return getattr(wp, 'mat33')
    if block_size == 4:
        return getattr(wp, 'mat44')
    raise ValueError(f'unsupported warp block size: {block_size}')


def _warp_solver_iterations(result: Any) -> int:
    if isinstance(result, tuple) and result:
        first = result[0]
        if hasattr(first, 'numpy'):
            try:
                arr = np.asarray(first.numpy()).reshape(-1)
                if arr.size:
                    return int(arr[0])
            except Exception:
                return 0
        try:
            return int(first)
        except Exception:
            return 0
    try:
        return int(result)
    except Exception:
        return 0


def _warp_solution_to_numpy(x_wp: Any, expected_size: int, block_size: int = 1) -> np.ndarray:
    if hasattr(x_wp, 'numpy'):
        x = np.asarray(x_wp.numpy(), dtype=float)
    else:
        x = np.asarray(x_wp, dtype=float)
    if x.ndim > 1:
        x = x.reshape(-1)
    else:
        x = x.reshape(-1)
    if int(expected_size) > 0 and x.size != int(expected_size):
        if block_size > 1 and x.size * int(block_size) == int(expected_size):
            x = x.reshape(-1)
        else:
            raise ValueError(f'warp solver returned solution of size {x.size}, expected {expected_size}')
    return x



def _scipy_to_block_triplets(A: Any, block_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sp = _optional_import('scipy.sparse')
    if sp is None or not getattr(sp, 'issparse', lambda *_: False)(A):
        raise TypeError('expected a scipy sparse matrix')
    A_csr = A.tocsr()
    n = int(A_csr.shape[0])
    bs = max(1, int(block_size))
    if n % bs != 0:
        raise ValueError(f'matrix dimension {n} is not divisible by block_size={bs}')
    if bs == 1:
        coo = A_csr.tocoo()
        return np.asarray(coo.row, dtype=np.int32), np.asarray(coo.col, dtype=np.int32), np.asarray(coo.data, dtype=np.float32)
    rows: list[int] = []
    cols: list[int] = []
    vals: list[np.ndarray] = []
    nblocks = n // bs
    for bi in range(nblocks):
        r0 = bi * bs
        r1 = r0 + bs
        row_block = A_csr[r0:r1]
        touched_cols: dict[int, np.ndarray] = {}
        for local_r in range(bs):
            start = row_block.indptr[local_r]
            stop = row_block.indptr[local_r + 1]
            cols_r = row_block.indices[start:stop]
            data_r = row_block.data[start:stop]
            for col, val in zip(cols_r, data_r, strict=False):
                bj = int(col) // bs
                c0 = bj * bs
                local_c = int(col) - c0
                block = touched_cols.get(bj)
                if block is None:
                    block = np.zeros((bs, bs), dtype=np.float32)
                    touched_cols[bj] = block
                block[local_r, local_c] += np.float32(val)
        for bj, block in touched_cols.items():
            rows.append(bi)
            cols.append(int(bj))
            vals.append(block)
    return np.asarray(rows, dtype=np.int32), np.asarray(cols, dtype=np.int32), np.asarray(vals, dtype=np.float32)



def _apply_dirichlet_penalty_sparse(A: Any, rhs: np.ndarray, fixed_dofs: np.ndarray, fixed_values: np.ndarray, penalty: float) -> tuple[Any, np.ndarray]:
    sp = _optional_import('scipy.sparse')
    if sp is None or not getattr(sp, 'issparse', lambda *_: False)(A):
        raise TypeError('expected a scipy sparse matrix for dirichlet penalty application')
    if fixed_dofs.size == 0:
        return A, np.asarray(rhs, dtype=float)
    A_mod = A.tolil(copy=True)
    b_mod = np.asarray(rhs, dtype=float).copy()
    for dof, value in zip(np.asarray(fixed_dofs, dtype=np.int64), np.asarray(fixed_values, dtype=float), strict=False):
        A_mod[int(dof), int(dof)] = float(A_mod[int(dof), int(dof)]) + float(penalty)
        b_mod[int(dof)] += float(penalty) * float(value)
    return A_mod.tocsr(), b_mod


@lru_cache(maxsize=1)
def _get_warp_block_modifier_bundle() -> Any | None:
    wp = _optional_import('warp')
    if wp is None:
        return None

    @wp.kernel
    def _add_regularization_kernel(block_values: wp.array3d(dtype=wp.float32), diag_slots: wp.array(dtype=wp.int32), value: float):
        i = wp.tid()
        slot = diag_slots[i]
        if slot >= 0:
            wp.atomic_add(block_values, slot, 0, 0, value)
            wp.atomic_add(block_values, slot, 1, 1, value)
            wp.atomic_add(block_values, slot, 2, 2, value)

    @wp.kernel
    def _apply_dirichlet_penalty_kernel(block_values: wp.array3d(dtype=wp.float32), rhs: wp.array(dtype=wp.float32), diag_slots: wp.array(dtype=wp.int32), fixed_dofs: wp.array(dtype=wp.int32), fixed_values: wp.array(dtype=wp.float32), penalty: float):
        i = wp.tid()
        dof = fixed_dofs[i]
        node = dof // 3
        comp = dof - 3 * node
        slot = diag_slots[node]
        if slot >= 0:
            wp.atomic_add(block_values, slot, comp, comp, penalty)
            wp.atomic_add(rhs, dof, penalty * fixed_values[i])

    return wp, _add_regularization_kernel, _apply_dirichlet_penalty_kernel


def _try_warp_block_sparse_solve(
    matrix: Any,
    rhs: np.ndarray,
    *,
    regularization: float,
    symmetric: bool,
    metadata: dict[str, Any] | None,
    block_size: int,
    compute_device: str,
    context: LinearSolverContext | None,
    tol: float,
    maxiter: int,
    fixed_dofs: np.ndarray | None = None,
    fixed_values: np.ndarray | None = None,
) -> tuple[np.ndarray, LinearSolveInfo] | None:
    meta = metadata or {}
    if not bool(meta.get('warp_full_gpu_linear_solve', False)) or not _is_custom_block_sparse_matrix(matrix):
        return None
    if int(block_size) != 3:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError('full-gpu block sparse solve currently requires block_size=3')
        return None
    wp = _optional_import('warp')
    wp_sparse = _optional_import('warp.sparse')
    wp_linear = _optional_import('warp.optim.linear')
    if wp is None or wp_sparse is None or wp_linear is None:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError('warp full-gpu block sparse solve requested, but warp sparse modules are unavailable')
        return None
    device = str(compute_device or meta.get('warp_device', getattr(matrix, 'device', 'cuda:0'))).lower()
    if device in {'auto', 'cuda'}:
        device = 'cuda:0'
    if not device.startswith('cuda'):
        device = 'cuda:0'
    try:
        wp.init()
        if hasattr(wp, 'set_device'):
            wp.set_device(device)
    except Exception as exc:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'failed to initialize Warp on {device}: {exc}') from exc
        return None
    bundle = _get_warp_block_modifier_bundle()
    if bundle is None:
        return None
    _wp2, reg_kernel, bc_kernel = bundle
    from geoai_simkit.solver.warp_hex8 import clone_warp_block_values, get_pattern_device_arrays
    block_type = _warp_block_type(wp, 3)
    source_values_dev = getattr(matrix, 'values_device', None)
    values_dev = source_values_dev
    rows_wp, cols_wp, diag_slots_wp = get_pattern_device_arrays(matrix.pattern, device, wp)
    if values_dev is None:
        vals_np = np.asarray(matrix.host_values(), dtype=np.float32)
        values_dev = wp.from_numpy(vals_np, dtype=block_type, device=device)
    else:
        values_dev = clone_warp_block_values(values_dev, wp, block_type, device)
    rhs_wp = wp.from_numpy(np.asarray(rhs, dtype=np.float32), dtype=wp.float32, device=device)
    if regularization > 0.0 and int(matrix.pattern.diag_block_slots.size) > 0:
        wp.launch(kernel=reg_kernel, dim=int(matrix.pattern.diag_block_slots.size), inputs=[values_dev, diag_slots_wp, float(regularization)], device=device)
    fd = np.asarray(fixed_dofs if fixed_dofs is not None else np.empty((0,), dtype=np.int64), dtype=np.int32)
    fv = np.asarray(fixed_values if fixed_values is not None else np.empty((0,), dtype=float), dtype=np.float32)
    if fd.size:
        penalty = float(meta.get('dirichlet_penalty', max(1.0e8, 1.0e6 / max(float(regularization), 1.0e-12))))
        fd_wp = wp.from_numpy(fd, dtype=wp.int32, device=device)
        fv_wp = wp.from_numpy(fv, dtype=wp.float32, device=device)
        wp.launch(kernel=bc_kernel, dim=int(fd.size), inputs=[values_dev, rhs_wp, diag_slots_wp, fd_wp, fv_wp, penalty], device=device)
    sync = getattr(wp, 'synchronize_device', None)
    if callable(sync):
        sync(device)
    elif hasattr(wp, 'synchronize'):
        wp.synchronize()
    nblock = int(matrix.ndof) // 3
    try:
        A_wp = wp_sparse.bsr_from_triplets(rows_of_blocks=nblock, cols_of_blocks=nblock, rows=rows_wp, columns=cols_wp, values=values_dev)
    except Exception:
        vals_np = np.asarray(matrix.host_values(), dtype=np.float32)
        values_dev = wp.from_numpy(vals_np, dtype=block_type, device=device)
        if regularization > 0.0 and int(matrix.pattern.diag_block_slots.size) > 0:
            wp.launch(kernel=reg_kernel, dim=int(matrix.pattern.diag_block_slots.size), inputs=[values_dev, diag_slots_wp, float(regularization)], device=device)
        if fd.size:
            penalty = float(meta.get('dirichlet_penalty', max(1.0e8, 1.0e6 / max(float(regularization), 1.0e-12))))
            fd_wp = wp.from_numpy(fd, dtype=wp.int32, device=device)
            fv_wp = wp.from_numpy(fv, dtype=wp.float32, device=device)
            wp.launch(kernel=bc_kernel, dim=int(fd.size), inputs=[values_dev, rhs_wp, diag_slots_wp, fd_wp, fv_wp, penalty], device=device)
        A_wp = wp_sparse.bsr_from_triplets(rows_of_blocks=nblock, cols_of_blocks=nblock, rows=rows_wp, columns=cols_wp, values=values_dev)

    x0 = wp.zeros_like(rhs_wp)
    precond_name = str(meta.get('warp_preconditioner', 'diag')).lower()
    precond = None
    precond_fn = getattr(wp_linear, 'preconditioner', None)
    if callable(precond_fn):
        for kwargs in ({'kind': precond_name}, {'type': precond_name}, {}):
            try:
                precond = precond_fn(A_wp, **kwargs)
                break
            except TypeError:
                continue
            except Exception:
                break
    solver_name = str(meta.get('warp_solver', 'cg' if symmetric else 'bicgstab')).lower()
    solver_fn = getattr(wp_linear, solver_name, None)
    if solver_fn is None:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'warp solver {solver_name!r} is unavailable')
        return None
    result = None
    last_exc: Exception | None = None
    attempts = []
    if precond is not None:
        attempts.append({'x': x0, 'M': precond, 'tol': tol, 'maxiter': maxiter, 'check_every': 0})
        attempts.append({'x': x0, 'M': precond, 'tol': tol, 'maxiter': maxiter})
    attempts.append({'x': x0, 'tol': tol, 'maxiter': maxiter, 'check_every': 0})
    attempts.append({'x': x0, 'tol': tol, 'maxiter': maxiter})
    for kwargs in attempts:
        try:
            result = solver_fn(A_wp, rhs_wp, **kwargs)
            break
        except TypeError as exc:
            last_exc = exc
        except Exception as exc:
            last_exc = exc
    if result is None:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'warp block sparse solve failed: {last_exc}') from last_exc
        return None
    sync = getattr(wp, 'synchronize_device', None)
    if callable(sync):
        sync(device)
    elif hasattr(wp, 'synchronize'):
        wp.synchronize()
    x = _warp_solution_to_numpy(x0, expected_size=int(np.asarray(rhs).size), block_size=block_size)
    iterations = max(1, _warp_solver_iterations(result))
    return x, LinearSolveInfo(
        backend=f'warp-bsr-{solver_name}',
        regularization=regularization,
        used_sparse=True,
        iterations=iterations,
        warnings=[],
        ordering='natural',
        preconditioner=precond_name if precond is not None else 'none',
        symmetric=bool(symmetric),
        reused_pattern=False,
        reused_factorization=False,
        block_size=3,
        device=device,
    )


def _try_warp_sparse_solve(
    matrix: Any,
    rhs: np.ndarray,
    *,
    regularization: float,
    symmetric: bool,
    metadata: dict[str, Any] | None,
    block_size: int,
    compute_device: str,
    context: LinearSolverContext | None,
    tol: float,
    maxiter: int,
) -> tuple[np.ndarray, LinearSolveInfo] | None:
    meta = metadata or {}
    if not bool(meta.get('warp_full_gpu_linear_solve', False)):
        return None
    wp = _optional_import('warp')
    wp_sparse = _optional_import('warp.sparse')
    wp_linear = _optional_import('warp.optim.linear')
    sp = _optional_import('scipy.sparse')
    if wp is None or wp_sparse is None or wp_linear is None or sp is None or not getattr(sp, 'issparse', lambda *_: False)(matrix):
        if bool(meta.get('require_warp', False)):
            raise RuntimeError('warp full-gpu linear solve requested, but warp/scipy sparse support is unavailable')
        return None
    device = str(compute_device or meta.get('warp_device', 'cuda:0')).lower()
    if device == 'auto' or device == 'cuda':
        device = 'cuda:0'
    if not device.startswith('cuda'):
        device = 'cuda:0'
    try:
        wp.init()
        if hasattr(wp, 'set_device'):
            wp.set_device(device)
    except Exception as exc:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'failed to initialize Warp on {device}: {exc}') from exc
        return None

    A = matrix.tocsr().astype(np.float32)
    n = int(A.shape[0])
    A = A + sp.eye(n, format='csr', dtype=np.float32) * np.float32(regularization)
    rows_np, cols_np, vals_np = _scipy_to_block_triplets(A, block_size=max(1, int(block_size)))
    block_type = _warp_block_type(wp, max(1, int(block_size)))
    rows_wp = wp.from_numpy(rows_np, dtype=wp.int32, device=device)
    cols_wp = wp.from_numpy(cols_np, dtype=wp.int32, device=device)
    vals_wp = wp.from_numpy(vals_np, dtype=block_type, device=device)
    nblock = n // max(1, int(block_size))
    A_wp = wp_sparse.bsr_from_triplets(
        rows_of_blocks=nblock,
        cols_of_blocks=nblock,
        rows=rows_wp,
        columns=cols_wp,
        values=vals_wp,
    )
    b_wp = wp.from_numpy(np.asarray(rhs, dtype=np.float32), dtype=wp.float32, device=device)
    x0 = wp.zeros_like(b_wp)
    precond_name = str(meta.get('warp_preconditioner', 'diag')).lower()
    precond = None
    precond_fn = getattr(wp_linear, 'preconditioner', None)
    if callable(precond_fn):
        for kwargs in (
            {'kind': precond_name},
            {'type': precond_name},
            {},
        ):
            try:
                precond = precond_fn(A_wp, **kwargs)
                break
            except TypeError:
                continue
            except Exception:
                break
    solver_name = str(meta.get('warp_solver', 'cg' if symmetric else 'bicgstab')).lower()
    solver_fn = getattr(wp_linear, solver_name, None)
    if solver_fn is None:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'warp solver {solver_name!r} is unavailable')
        return None
    result = None
    call_attempts = []
    if precond is not None:
        call_attempts.append({'x': x0, 'M': precond, 'tol': tol, 'maxiter': maxiter, 'check_every': 0})
        call_attempts.append({'x': x0, 'M': precond, 'tol': tol, 'maxiter': maxiter})
    call_attempts.append({'x': x0, 'tol': tol, 'maxiter': maxiter, 'check_every': 0})
    call_attempts.append({'x': x0, 'tol': tol, 'maxiter': maxiter})
    last_exc: Exception | None = None
    for kwargs in call_attempts:
        try:
            result = solver_fn(A_wp, b_wp, **kwargs)
            break
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            continue
    if result is None:
        if bool(meta.get('require_warp', False)):
            raise RuntimeError(f'warp sparse solve failed: {last_exc}') from last_exc
        return None
    sync = getattr(wp, 'synchronize_device', None)
    if callable(sync):
        sync(device)
    elif hasattr(wp, 'synchronize'):
        wp.synchronize()
    x = _warp_solution_to_numpy(x0, expected_size=int(np.asarray(rhs).size), block_size=max(1, int(block_size)))
    iterations = max(1, _warp_solver_iterations(result))
    return x, LinearSolveInfo(
        backend=f'warp-{solver_name}',
        regularization=regularization,
        used_sparse=True,
        iterations=iterations,
        warnings=[],
        ordering='natural',
        preconditioner=precond_name if precond is not None else 'none',
        symmetric=bool(symmetric),
        reused_pattern=False,
        reused_factorization=False,
        block_size=max(1, int(block_size)),
        device=device,
    )



def solve_linear_system(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    prefer_sparse: bool = True,
    sparse_threshold: int = 400,
    regularization_floor: float = 1.0e-9,
    regularization_scale: float = 1.0e-10,
    thread_count: int = 0,
    assume_symmetric: bool | None = None,
    context: LinearSolverContext | None = None,
    metadata: dict[str, Any] | None = None,
    block_size: int = 1,
    compute_device: str = 'cpu',
    fixed_dofs: np.ndarray | None = None,
    fixed_values: np.ndarray | None = None,
) -> tuple[np.ndarray, LinearSolveInfo]:
    tc = configure_linear_algebra_threads(thread_count)
    b = np.asarray(rhs, dtype=float)
    meta = metadata or {}

    sp = _optional_import('scipy.sparse')
    spla = _optional_import('scipy.sparse.linalg')
    custom_block = _is_custom_block_sparse_matrix(matrix)
    fixed_dofs_arr = np.asarray(fixed_dofs if fixed_dofs is not None else np.empty((0,), dtype=np.int64), dtype=np.int64)
    fixed_values_arr = np.asarray(fixed_values if fixed_values is not None else np.empty((0,), dtype=float), dtype=float)
    if custom_block:
        n = int(matrix.ndof)
        diag = np.array([1.0], dtype=float)
        A_sparse = None
        A_dense = None
        is_sparse = False
    else:
        is_sparse = bool(sp is not None and getattr(sp, 'issparse', lambda *_: False)(matrix))
        if is_sparse:
            A_sparse = matrix.tocsr().astype(float)
            n = int(A_sparse.shape[0])
            diag = np.abs(np.asarray(A_sparse.diagonal(), dtype=float)) if n else np.array([1.0])
            A_dense = None
        else:
            A_dense = np.asarray(matrix, dtype=float)
            if A_dense.size == 0:
                return np.empty((0,), dtype=float), LinearSolveInfo(backend='empty', regularization=0.0, thread_count=tc)
            n = int(A_dense.shape[0])
            diag = np.abs(np.diag(A_dense)) if A_dense.ndim == 2 and A_dense.shape[0] else np.array([1.0])
            A_sparse = None

    reg = max(regularization_floor, regularization_scale * float(np.max(diag) if diag.size else 1.0))
    warnings: list[str] = []
    use_sparse = bool(prefer_sparse and n >= sparse_threshold and sp is not None and spla is not None)
    symmetric = bool(assume_symmetric if assume_symmetric is not None else _is_probably_symmetric(matrix))
    ordering = _choose_ordering(meta, symmetric)
    block_size = max(1, int(meta.get('block_size', block_size)))

    if context is not None:
        context.solve_count += 1

    if custom_block:
        try:
            warp_block_result = _try_warp_block_sparse_solve(
                matrix,
                b,
                regularization=reg,
                symmetric=symmetric,
                metadata=meta,
                block_size=block_size,
                compute_device=compute_device,
                context=context,
                tol=float(meta.get('iterative_tolerance', 1.0e-10)),
                maxiter=int(meta.get('iterative_maxiter', max(500, min(4000, 2 * max(1, n))))),
                fixed_dofs=fixed_dofs_arr,
                fixed_values=fixed_values_arr,
            )
            if warp_block_result is not None:
                x, info = warp_block_result
                info.thread_count = tc
                info.symmetric = symmetric
                return np.asarray(x, dtype=float), info
        except Exception:
            if bool(meta.get('require_warp', False)):
                raise
        matrix = matrix.to_csr()
        is_sparse = True
        A_sparse = matrix.tocsr().astype(float)
        A_dense = None

    if use_sparse or is_sparse:
        try:
            Asp = A_sparse if A_sparse is not None else sp.csr_matrix(A_dense)
            if fixed_dofs_arr.size:
                penalty = float(meta.get('dirichlet_penalty', max(1.0e8, 1.0e6 / max(reg, 1.0e-12))))
                Asp, b = _apply_dirichlet_penalty_sparse(Asp, b, fixed_dofs_arr, fixed_values_arr, penalty)
            perm, inv_perm, reused_pattern, reorder_warnings = _compute_permutation(Asp, ordering, symmetric, context)
            warnings.extend(reorder_warnings)
            Asp_perm, b_perm = _apply_permutation(Asp, b, perm)

            warp_result = _try_warp_sparse_solve(
                Asp_perm,
                b_perm,
                regularization=reg,
                symmetric=symmetric,
                metadata=meta,
                block_size=block_size,
                compute_device=compute_device,
                context=context,
                tol=float(meta.get('iterative_tolerance', 1.0e-10)),
                maxiter=int(meta.get('iterative_maxiter', max(500, min(4000, 2 * max(1, n))))),
            )
            if warp_result is not None:
                x_perm, info = warp_result
                x = _restore_permutation(x_perm, inv_perm)
                info.thread_count = tc
                info.ordering = ordering
                info.reused_pattern = reused_pattern
                info.symmetric = symmetric
                return np.asarray(x, dtype=float), info

            Asp_reg = Asp_perm + sp.eye(n, format='csr') * reg
            precond_name = str(meta.get('preconditioner', 'auto')).lower()
            M = None
            reused_prec = False
            if precond_name == 'auto':
                precond_name = 'block-jacobi' if symmetric and block_size > 1 else 'spilu'
            if precond_name == 'block-jacobi':
                M, reused_prec, prec_warnings = _build_block_jacobi_preconditioner(Asp_reg, block_size, reg, context)
                warnings.extend(prec_warnings)
            elif precond_name in {'spilu', 'ilu'}:
                M, reused_prec, prec_warnings = _build_spilu_preconditioner(Asp_reg, meta, context)
                warnings.extend(prec_warnings)
                precond_name = 'spilu'
            elif precond_name == 'jacobi':
                diag_reg = np.asarray(Asp_reg.diagonal(), dtype=float)
                diag_reg = np.where(np.abs(diag_reg) > 1e-14, diag_reg, 1.0)
                M = sp.diags(1.0 / diag_reg, format='csr')
            else:
                precond_name = 'none'

            direct_preference = str(meta.get('solver_strategy', 'auto')).lower()
            iter_tol = float(meta.get('iterative_tolerance', 1.0e-10))
            iter_max = int(meta.get('iterative_maxiter', max(500, min(5000, 2 * max(1, n)))))
            methods: list[tuple[str, Any]] = []
            if direct_preference == 'auto':
                if symmetric:
                    methods.extend([('cg', getattr(spla, 'cg', None)), ('minres', getattr(spla, 'minres', None))])
                else:
                    methods.extend([('bicgstab', getattr(spla, 'bicgstab', None)), ('gmres', getattr(spla, 'gmres', None))])
            elif direct_preference == 'direct':
                methods = []
            else:
                methods.append((direct_preference, getattr(spla, direct_preference, None)))

            for method_name, method in methods:
                if method is None:
                    continue
                try:
                    kwargs = {'rtol': iter_tol, 'atol': 0.0, 'maxiter': iter_max, 'M': M}
                    if method_name == 'gmres':
                        kwargs['restart'] = int(meta.get('gmres_restart', 50))
                    x_perm, info_code = method(Asp_reg, b_perm, **kwargs)
                    x_perm = np.asarray(x_perm, dtype=float)
                    if info_code == 0 and np.all(np.isfinite(x_perm)):
                        x = _restore_permutation(x_perm, inv_perm)
                        return x, LinearSolveInfo(
                            backend=f'scipy-{method_name}',
                            regularization=reg,
                            used_sparse=True,
                            iterations=iter_max,
                            warnings=warnings,
                            thread_count=tc,
                            ordering=ordering,
                            preconditioner=precond_name,
                            symmetric=symmetric,
                            reused_pattern=reused_pattern,
                            reused_factorization=bool(reused_prec),
                            block_size=block_size,
                            device='cpu',
                        )
                    warnings.append(f'{method_name} fallback: info={info_code}')
                except TypeError:
                    try:
                        # Older SciPy variants may use tol instead of rtol.
                        kwargs = {'tol': iter_tol, 'maxiter': iter_max, 'M': M}
                        if method_name == 'gmres':
                            kwargs['restart'] = int(meta.get('gmres_restart', 50))
                        x_perm, info_code = method(Asp_reg, b_perm, **kwargs)
                        x_perm = np.asarray(x_perm, dtype=float)
                        if info_code == 0 and np.all(np.isfinite(x_perm)):
                            x = _restore_permutation(x_perm, inv_perm)
                            return x, LinearSolveInfo(
                                backend=f'scipy-{method_name}',
                                regularization=reg,
                                used_sparse=True,
                                iterations=iter_max,
                                warnings=warnings,
                                thread_count=tc,
                                ordering=ordering,
                                preconditioner=precond_name,
                                symmetric=symmetric,
                                reused_pattern=reused_pattern,
                                reused_factorization=bool(reused_prec),
                                block_size=block_size,
                                device='cpu',
                            )
                        warnings.append(f'{method_name} fallback: info={info_code}')
                    except Exception as exc:
                        warnings.append(f'{method_name} fallback: {exc}')
                except Exception as exc:
                    warnings.append(f'{method_name} fallback: {exc}')

            matrix_hash = _matrix_data_hash(Asp_reg)
            if context is not None and context.factorization_key == ('splu', matrix_hash) and context.factorization is not None:
                try:
                    x_perm = np.asarray(context.factorization.solve(b_perm), dtype=float)
                    x = _restore_permutation(x_perm, inv_perm)
                    return x, LinearSolveInfo(
                        backend='scipy-splu-reuse',
                        regularization=reg,
                        used_sparse=True,
                        warnings=warnings,
                        thread_count=tc,
                        ordering=ordering,
                        preconditioner='none',
                        symmetric=symmetric,
                        reused_pattern=reused_pattern,
                        reused_factorization=True,
                        block_size=block_size,
                        device='cpu',
                    )
                except Exception as exc:
                    warnings.append(f'splu reuse fallback: {exc}')

            cholmod = _optional_import('sksparse.cholmod')
            if symmetric and cholmod is not None and direct_preference in {'auto', 'direct', 'cholmod'}:
                try:
                    factor = cholmod.cholesky(Asp_reg.tocsc())
                    x_perm = np.asarray(factor(b_perm), dtype=float)
                    if context is not None:
                        context.factorization_key = ('cholmod', matrix_hash)
                        context.factorization = factor
                    x = _restore_permutation(x_perm, inv_perm)
                    return x, LinearSolveInfo(
                        backend='cholmod',
                        regularization=reg,
                        used_sparse=True,
                        warnings=warnings,
                        thread_count=tc,
                        ordering=ordering,
                        preconditioner='none',
                        symmetric=symmetric,
                        reused_pattern=reused_pattern,
                        reused_factorization=False,
                        block_size=block_size,
                        device='cpu',
                    )
                except Exception as exc:
                    warnings.append(f'cholmod fallback: {exc}')

            permc_spec = 'COLAMD'
            if ordering == 'mmd_ata':
                permc_spec = 'MMD_ATA'
            elif ordering in {'amd', 'colamd'}:
                permc_spec = 'COLAMD'
            elif ordering == 'mmd_at_plus_a':
                permc_spec = 'MMD_AT_PLUS_A'
            elif ordering == 'natural':
                permc_spec = 'NATURAL'
            lu = spla.splu(Asp_reg.tocsc(), permc_spec=permc_spec)
            if context is not None:
                context.factorization_key = ('splu', matrix_hash)
                context.factorization = lu
            x_perm = np.asarray(lu.solve(b_perm), dtype=float)
            x = _restore_permutation(x_perm, inv_perm)
            return x, LinearSolveInfo(
                backend='scipy-splu',
                regularization=reg,
                used_sparse=True,
                warnings=warnings,
                thread_count=tc,
                ordering=ordering,
                preconditioner='none',
                symmetric=symmetric,
                reused_pattern=reused_pattern,
                reused_factorization=False,
                block_size=block_size,
                device='cpu',
            )
        except Exception as exc:  # pragma: no cover - sparse path optional / platform dependent
            warnings.append(f'sparse solver fallback: {exc}')

    Areg = A_dense + np.eye(n, dtype=float) * reg if A_dense is not None else (A_sparse + sp.eye(n, format='csr') * reg).toarray()
    try:
        x = np.linalg.solve(Areg, b)
        return np.asarray(x, dtype=float), LinearSolveInfo(
            backend='numpy-dense',
            regularization=reg,
            used_sparse=False,
            warnings=warnings,
            thread_count=tc,
            ordering='natural',
            preconditioner='none',
            symmetric=symmetric,
            block_size=1,
            device='cpu',
        )
    except np.linalg.LinAlgError:
        warnings.append('dense solve singular; using least-squares fallback')
        x, *_ = np.linalg.lstsq(Areg, b, rcond=None)
        return np.asarray(x, dtype=float), LinearSolveInfo(
            backend='numpy-lstsq',
            regularization=reg,
            used_sparse=False,
            warnings=warnings,
            thread_count=tc,
            ordering='natural',
            preconditioner='none',
            symmetric=symmetric,
            block_size=1,
            device='cpu',
        )
