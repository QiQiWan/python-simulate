from __future__ import annotations

from dataclasses import dataclass

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    class _DummyUnstructuredGrid:
        pass
    class _CellType:
        TETRA = 10
    class _PVStub:
        UnstructuredGrid = _DummyUnstructuredGrid
        CellType = _CellType
    pv = _PVStub()

from geoai_simkit.core.model import BoundaryCondition, LoadDefinition
from geoai_simkit.solver.hex8_linear import (
    LinearRegionMaterial,
    apply_stage_nodal_loads,
    build_partition_local_matrix_summaries,
    isotropic_D,
    select_bc_nodes,
    von_mises,
)
from geoai_simkit.solver.linsys.sparse_block import SparseBlockMatrix
from geoai_simkit.solver.linear_algebra import LinearSolverContext, _optional_import, solve_linear_system


@dataclass(slots=True)
class Tet4Submesh:
    global_point_ids: np.ndarray
    points: np.ndarray
    elements: np.ndarray
    full_cell_ids: np.ndarray
    local_by_global: dict[int, int]


TET4_CELL_TYPE = 10


def _build_element_dof_map(elements: np.ndarray) -> np.ndarray:
    elems = np.asarray(elements, dtype=np.int64)
    edofs = np.empty((elems.shape[0], 12), dtype=np.int64)
    for a in range(4):
        base = 3 * elems[:, a]
        edofs[:, 3 * a + 0] = base + 0
        edofs[:, 3 * a + 1] = base + 1
        edofs[:, 3 * a + 2] = base + 2
    return edofs


def _canonical_element_signature(coords: np.ndarray, decimals: int = 10) -> tuple[float, ...]:
    rel = np.asarray(coords, dtype=float) - np.min(coords, axis=0, keepdims=True)
    order = np.lexsort((rel[:, 2], rel[:, 1], rel[:, 0]))
    return tuple(np.round(rel[order].reshape(-1), decimals=decimals).tolist())


def extract_tet4_submesh(grid: pv.UnstructuredGrid) -> Tet4Submesh:
    tet_cell_ids: list[int] = []
    connectivity: list[np.ndarray] = []
    for cid in range(int(getattr(grid, 'n_cells', 0) or 0)):
        ctype = int(grid.celltypes[cid])
        if ctype != TET4_CELL_TYPE:
            continue
        cell = grid.get_cell(cid)
        pids = np.asarray(cell.point_ids, dtype=np.int64)
        if pids.size != 4:
            continue
        tet_cell_ids.append(cid)
        connectivity.append(pids)
    if not connectivity:
        return Tet4Submesh(
            global_point_ids=np.empty((0,), dtype=np.int64),
            points=np.empty((0, 3), dtype=float),
            elements=np.empty((0, 4), dtype=np.int64),
            full_cell_ids=np.empty((0,), dtype=np.int64),
            local_by_global={},
        )
    conn = np.asarray(connectivity, dtype=np.int64)
    unique_pids = np.unique(conn.reshape(-1))
    local_conn = np.searchsorted(unique_pids, conn)
    local_by_global = {int(g): i for i, g in enumerate(unique_pids.tolist())}
    return Tet4Submesh(
        global_point_ids=unique_pids,
        points=np.asarray(grid.points[unique_pids], dtype=float),
        elements=np.asarray(local_conn, dtype=np.int64),
        full_cell_ids=np.asarray(tet_cell_ids, dtype=np.int64),
        local_by_global=local_by_global,
    )


def subset_tet4_submesh(base: Tet4Submesh, mask: np.ndarray) -> Tet4Submesh:
    elems = np.asarray(base.elements[mask], dtype=np.int64)
    full_ids = np.asarray(base.full_cell_ids[mask], dtype=np.int64)
    if elems.size == 0:
        return Tet4Submesh(
            global_point_ids=np.empty((0,), dtype=np.int64),
            points=np.empty((0, 3), dtype=float),
            elements=np.empty((0, 4), dtype=np.int64),
            full_cell_ids=np.empty((0,), dtype=np.int64),
            local_by_global={},
        )
    used_local = np.unique(elems.reshape(-1))
    new_elems = np.searchsorted(used_local, elems)
    new_points = np.asarray(base.points[used_local], dtype=float)
    new_global = np.asarray(base.global_point_ids[used_local], dtype=np.int64)
    local_by_global = {int(g): i for i, g in enumerate(new_global.tolist())}
    return Tet4Submesh(
        global_point_ids=new_global,
        points=new_points,
        elements=np.asarray(new_elems, dtype=np.int64),
        full_cell_ids=full_ids,
        local_by_global=local_by_global,
    )


def bmatrix_tet4(coords: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    xyz = np.asarray(coords, dtype=float)
    if xyz.shape != (4, 3):
        raise ValueError(f'Tet4 element expects shape (4, 3), got {xyz.shape}')
    A = np.column_stack((np.ones(4, dtype=float), xyz))
    detA = float(np.linalg.det(A))
    volume = abs(detA) / 6.0
    if volume <= 1.0e-15:
        raise ValueError('Degenerate Tet4 element encountered')
    invA = np.linalg.inv(A)
    dN_dx = invA[1:, :].T
    B = np.zeros((6, 12), dtype=float)
    for a in range(4):
        ix = 3 * a
        B[0, ix] = dN_dx[a, 0]
        B[1, ix + 1] = dN_dx[a, 1]
        B[2, ix + 2] = dN_dx[a, 2]
        B[3, ix] = dN_dx[a, 1]
        B[3, ix + 1] = dN_dx[a, 0]
        B[4, ix + 1] = dN_dx[a, 2]
        B[4, ix + 2] = dN_dx[a, 1]
        B[5, ix] = dN_dx[a, 2]
        B[5, ix + 2] = dN_dx[a, 0]
    return B, volume, dN_dx


def element_stiffness_tet4(coords: np.ndarray, D: np.ndarray) -> np.ndarray:
    B, volume, _ = bmatrix_tet4(coords)
    return B.T @ D @ B * volume


def element_body_force_tet4(coords: np.ndarray, rho: float, gravity: tuple[float, float, float]) -> np.ndarray:
    fe = np.zeros(12, dtype=float)
    g = np.asarray(gravity, dtype=float)
    if np.linalg.norm(g) == 0.0 or rho == 0.0:
        return fe
    _, volume, _ = bmatrix_tet4(coords)
    nodal = rho * g * (volume / 4.0)
    for a in range(4):
        fe[3 * a: 3 * a + 3] = nodal
    return fe


def solve_linear_tet4(
    submesh: Tet4Submesh,
    cell_materials: list[LinearRegionMaterial],
    bcs: tuple[BoundaryCondition, ...],
    loads: tuple[LoadDefinition, ...],
    gravity: tuple[float, float, float],
    displacement_scale: float = 1.0,
    prefer_sparse: bool = True,
    thread_count: int = 0,
    compute_device: str = 'cpu',
    solver_metadata: dict[str, object] | None = None,
    progress_callback=None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object], np.ndarray, np.ndarray]:
    n_nodes = submesh.points.shape[0]
    ndof = n_nodes * 3
    if n_nodes == 0:
        return np.empty((0, 3)), np.empty((0, 6)), np.empty((0,)), {'backend': 'cpu-element-loop-tet4', 'device': str(compute_device), 'used_warp': False, 'warnings': []}

    sp = _optional_import('scipy.sparse')
    sparse_ok = bool(prefer_sparse and sp is not None and ndof >= 600)
    K = None if sparse_ok else np.zeros((ndof, ndof), dtype=float)
    F = np.zeros(ndof, dtype=float)
    cell_stresses = np.zeros((submesh.elements.shape[0], 6), dtype=float)
    element_dofs = _build_element_dof_map(submesh.elements)

    row_parts: list[np.ndarray] = []
    col_parts: list[np.ndarray] = []
    data_parts: list[np.ndarray] = []
    geom_cache: dict[tuple[float, ...], dict[str, np.ndarray | float]] = {}
    response_cache: dict[tuple[tuple[float, ...], float, float, float, tuple[float, float, float]], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    constitutive_cache: dict[tuple[float, float], np.ndarray] = {}
    assembly_info: dict[str, object] = {
        'backend': 'cpu-element-loop-tet4',
        'device': str(compute_device),
        'warnings': [],
        'used_warp': False,
        'element_family': 'tet4',
    }

    for eidx, elem in enumerate(submesh.elements):
        coords = submesh.points[elem]
        mat = cell_materials[eidx]
        edofs = element_dofs[eidx]
        shape_key = _canonical_element_signature(coords)
        mat_key = (float(mat.E), float(mat.nu))
        D = constitutive_cache.get(mat_key)
        if D is None:
            D = isotropic_D(mat.E, mat.nu)
            constitutive_cache[mat_key] = D

        cache_key = (shape_key, float(mat.E), float(mat.nu), float(mat.rho), tuple(float(v) for v in gravity))
        cached = response_cache.get(cache_key)
        if cached is None:
            Ke = element_stiffness_tet4(coords, D)
            fe = element_body_force_tet4(coords, mat.rho, gravity)
            B0, _, _ = bmatrix_tet4(coords)
            response_cache[cache_key] = (Ke, fe, B0)
        else:
            Ke, fe, B0 = cached

        if sparse_ok:
            row_parts.append(np.repeat(edofs, 12))
            col_parts.append(np.tile(edofs, 12))
            data_parts.append(np.asarray(Ke, dtype=float).reshape(-1))
        else:
            K[np.ix_(edofs, edofs)] += Ke
        F[edofs] += fe
        geom_cache[shape_key] = {'B0': B0, 'D': D}

    if sparse_ok:
        rows = np.concatenate(row_parts) if row_parts else np.empty((0,), dtype=np.int64)
        cols = np.concatenate(col_parts) if col_parts else np.empty((0,), dtype=np.int64)
        data = np.concatenate(data_parts) if data_parts else np.empty((0,), dtype=float)
        K = sp.coo_matrix((data, (rows, cols)), shape=(ndof, ndof)).tocsr()

    apply_stage_nodal_loads(F, submesh.points, loads, local_by_global=submesh.local_by_global)

    fixed_dofs: list[int] = []
    fixed_values: list[float] = []
    for bc in bcs:
        if bc.kind.lower() != 'displacement':
            continue
        node_ids = select_bc_nodes(submesh.points, bc, local_by_global=submesh.local_by_global)
        vals = np.asarray(bc.values, dtype=float)
        for nid in node_ids:
            for comp in bc.components:
                fixed_dofs.append(3 * int(nid) + int(comp))
                fixed_values.append(float(vals[min(int(comp), len(vals) - 1)]))
    fixed_dofs_arr = np.asarray(fixed_dofs, dtype=np.int64)
    fixed_values_arr = np.asarray(fixed_values, dtype=float)
    if fixed_dofs_arr.size == 0:
        zmin_nodes = np.where(np.isclose(submesh.points[:, 2], submesh.points[:, 2].min()))[0]
        if zmin_nodes.size:
            fixed_dofs_arr = np.concatenate([3 * zmin_nodes + 0, 3 * zmin_nodes + 1, 3 * zmin_nodes + 2]).astype(np.int64)
            fixed_values_arr = np.zeros(fixed_dofs_arr.size, dtype=float)

    all_dofs = np.arange(ndof, dtype=np.int64)
    free = np.setdiff1d(all_dofs, fixed_dofs_arr)
    matrix_summary = SparseBlockMatrix.from_matrix(
        K,
        block_size=3,
        metadata={
            'storage': 'csr' if sparse_ok else 'dense',
            'backend': assembly_info.get('backend'),
            'device': assembly_info.get('device'),
        },
    ).summary()
    assembly_info['linear_system_summary'] = {
        **matrix_summary,
        'rhs_size': int(np.asarray(F, dtype=float).size),
        'rhs_norm': float(np.linalg.norm(np.asarray(F, dtype=float).reshape(-1))),
        'rhs_max_abs': float(np.max(np.abs(np.asarray(F, dtype=float).reshape(-1)))) if np.asarray(F, dtype=float).size else 0.0,
        'fixed_dof_count': int(fixed_dofs_arr.size),
        'free_dof_count': int(free.size),
        'block_size': 3,
        'sparse_enabled': bool(sparse_ok),
    }
    u = np.zeros(ndof, dtype=float)
    if free.size:
        linear_context = LinearSolverContext()
        solver_meta = dict(solver_metadata or {})
        solver_meta.setdefault('block_size', 3)
        solver_meta.setdefault('preconditioner', 'block-jacobi')
        solver_meta.setdefault('ordering', 'rcm')
        F_eff = F[free].copy()
        if fixed_dofs_arr.size:
            if sparse_ok:
                F_eff -= K[free][:, fixed_dofs_arr] @ fixed_values_arr
            else:
                F_eff -= K[np.ix_(free, fixed_dofs_arr)] @ fixed_values_arr
        Kff = K[free][:, free] if sparse_ok else K[np.ix_(free, free)]
        u[free], solve_info = solve_linear_system(
            Kff,
            F_eff,
            prefer_sparse=prefer_sparse,
            thread_count=thread_count,
            assume_symmetric=True,
            context=linear_context,
            metadata=solver_meta,
            block_size=3,
            compute_device='cpu',
        )
        assembly_info['linear_solver'] = solve_info.backend
        assembly_info['linear_ordering'] = solve_info.ordering
        assembly_info['linear_preconditioner'] = solve_info.preconditioner
        assembly_info['linear_device'] = solve_info.device
        assembly_info['linear_system_summary'].update(
            {
                'solver_backend': solve_info.backend,
                'ordering': solve_info.ordering,
                'preconditioner': solve_info.preconditioner,
                'solver_device': solve_info.device,
            }
        )
        if solve_info.warnings:
            assembly_info.setdefault('warnings', []).extend(list(solve_info.warnings))
    if fixed_dofs_arr.size:
        u[fixed_dofs_arr] = fixed_values_arr

    if hasattr(K, 'dot'):
        Ku = np.asarray(K.dot(u), dtype=float).reshape(-1)
    else:
        Ku = np.asarray(K @ u, dtype=float).reshape(-1)
    equilibrium_residual = Ku - np.asarray(F, dtype=float).reshape(-1)
    reaction = np.zeros_like(equilibrium_residual)
    if fixed_dofs_arr.size:
        reaction[fixed_dofs_arr] = equilibrium_residual[fixed_dofs_arr]
        equilibrium_residual[fixed_dofs_arr] = 0.0

    assembly_info['linear_system_summary'].update(
        {
            'solution_size': int(u.size),
            'solution_norm': float(np.linalg.norm(np.asarray(u, dtype=float).reshape(-1))),
            'solution_max_abs': float(np.max(np.abs(np.asarray(u, dtype=float).reshape(-1)))) if np.asarray(u, dtype=float).size else 0.0,
            'residual_size': int(equilibrium_residual.size),
            'residual_norm': float(np.linalg.norm(equilibrium_residual)),
            'residual_max_abs': float(np.max(np.abs(equilibrium_residual))) if equilibrium_residual.size else 0.0,
            'reaction_size': int(reaction.size),
            'reaction_dof_count': int(fixed_dofs_arr.size),
            'reaction_norm': float(np.linalg.norm(reaction)),
            'reaction_max_abs': float(np.max(np.abs(reaction))) if reaction.size else 0.0,
        }
    )
    assembly_info['actual_partition_linear_systems'] = build_partition_local_matrix_summaries(
        K,
        submesh_global_point_ids=np.asarray(submesh.global_point_ids, dtype=np.int64),
        local_by_global=dict(submesh.local_by_global),
        solver_metadata=solver_metadata,
        block_size=3,
        matrix_metadata={
            'storage': str(matrix_summary.get('storage', 'csr')),
            'backend': assembly_info.get('backend'),
            'device': assembly_info.get('device'),
        },
        rhs=F,
        solution=u,
        residual=equilibrium_residual,
        reaction=reaction,
        fixed_dofs=fixed_dofs_arr,
        free_dofs=free,
    )

    u_nodes = u.reshape(n_nodes, 3)
    for eidx, elem in enumerate(submesh.elements):
        coords = submesh.points[elem]
        shape_key = _canonical_element_signature(coords)
        mat = cell_materials[eidx]
        D = constitutive_cache[(float(mat.E), float(mat.nu))]
        B0 = geom_cache[shape_key]['B0']
        ue = u[element_dofs[eidx]]
        strain = B0 @ ue
        cell_stresses[eidx] = D @ strain

    u_nodes *= displacement_scale
    vm = von_mises(cell_stresses)
    return (
        u_nodes,
        cell_stresses,
        vm,
        assembly_info,
        equilibrium_residual.reshape(n_nodes, 3),
        reaction.reshape(n_nodes, 3),
    )
