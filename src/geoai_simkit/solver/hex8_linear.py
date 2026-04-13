from __future__ import annotations

from dataclasses import dataclass

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    class _DummyUnstructuredGrid:
        pass
    class _CellType:
        HEXAHEDRON = 12
        VOXEL = 11
    class _PVStub:
        UnstructuredGrid = _DummyUnstructuredGrid
        CellType = _CellType
    pv = _PVStub()

from geoai_simkit.core.model import BoundaryCondition, LoadDefinition
from geoai_simkit.solver.linear_algebra import LinearSolverContext, _optional_import, solve_linear_system
from geoai_simkit.solver.warp_hex8 import build_block_sparse_pattern, resolve_warp_hex8_config, try_warp_hex8_linear_assembly


GAUSS = (-1.0 / np.sqrt(3.0), 1.0 / np.sqrt(3.0))


@dataclass(slots=True)
class Hex8Submesh:
    global_point_ids: np.ndarray
    points: np.ndarray
    elements: np.ndarray
    full_cell_ids: np.ndarray
    local_by_global: dict[int, int]


@dataclass(slots=True)
class LinearRegionMaterial:
    E: float
    nu: float
    rho: float = 0.0



def isotropic_D(E: float, nu: float) -> np.ndarray:
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    return np.array([
        [lam + 2 * mu, lam, lam, 0, 0, 0],
        [lam, lam + 2 * mu, lam, 0, 0, 0],
        [lam, lam, lam + 2 * mu, 0, 0, 0],
        [0, 0, 0, mu, 0, 0],
        [0, 0, 0, 0, mu, 0],
        [0, 0, 0, 0, 0, mu],
    ], dtype=float)



def shape_hex8(xi: float, eta: float, zeta: float) -> tuple[np.ndarray, np.ndarray]:
    N = 0.125 * np.array([
        (1 - xi) * (1 - eta) * (1 - zeta),
        (1 + xi) * (1 - eta) * (1 - zeta),
        (1 + xi) * (1 + eta) * (1 - zeta),
        (1 - xi) * (1 + eta) * (1 - zeta),
        (1 - xi) * (1 - eta) * (1 + zeta),
        (1 + xi) * (1 - eta) * (1 + zeta),
        (1 + xi) * (1 + eta) * (1 + zeta),
        (1 - xi) * (1 + eta) * (1 + zeta),
    ], dtype=float)
    dN = 0.125 * np.array([
        [-(1 - eta) * (1 - zeta), -(1 - xi) * (1 - zeta), -(1 - xi) * (1 - eta)],
        [+(1 - eta) * (1 - zeta), -(1 + xi) * (1 - zeta), -(1 + xi) * (1 - eta)],
        [+(1 + eta) * (1 - zeta), +(1 + xi) * (1 - zeta), -(1 + xi) * (1 + eta)],
        [-(1 + eta) * (1 - zeta), +(1 - xi) * (1 - zeta), -(1 - xi) * (1 + eta)],
        [-(1 - eta) * (1 + zeta), -(1 - xi) * (1 + zeta), +(1 - xi) * (1 - eta)],
        [+(1 - eta) * (1 + zeta), -(1 + xi) * (1 + zeta), +(1 + xi) * (1 - eta)],
        [+(1 + eta) * (1 + zeta), +(1 + xi) * (1 + zeta), +(1 + xi) * (1 + eta)],
        [-(1 + eta) * (1 + zeta), +(1 - xi) * (1 + zeta), +(1 - xi) * (1 + eta)],
    ], dtype=float)
    return N, dN



def bmatrix_hex8(coords: np.ndarray, xi: float, eta: float, zeta: float) -> tuple[np.ndarray, float, np.ndarray]:
    _, dN_dxi = shape_hex8(xi, eta, zeta)
    J = coords.T @ dN_dxi
    detJ = float(np.linalg.det(J))
    if detJ <= 1e-12:
        raise ValueError('Degenerate Hex8 element encountered')
    invJ = np.linalg.inv(J)
    dN_dx = dN_dxi @ invJ.T
    B = np.zeros((6, 24), dtype=float)
    for a in range(8):
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
    return B, detJ, dN_dx



def element_stiffness_hex8(coords: np.ndarray, D: np.ndarray) -> np.ndarray:
    Ke = np.zeros((24, 24), dtype=float)
    for xi in GAUSS:
        for eta in GAUSS:
            for zeta in GAUSS:
                B, detJ, _ = bmatrix_hex8(coords, xi, eta, zeta)
                Ke += B.T @ D @ B * detJ
    return Ke



def element_body_force_hex8(coords: np.ndarray, rho: float, gravity: tuple[float, float, float]) -> np.ndarray:
    fe = np.zeros(24, dtype=float)
    g = np.asarray(gravity, dtype=float)
    if np.linalg.norm(g) == 0.0 or rho == 0.0:
        return fe
    for xi in GAUSS:
        for eta in GAUSS:
            for zeta in GAUSS:
                N, dN = shape_hex8(xi, eta, zeta)
                J = coords.T @ dN
                detJ = float(np.linalg.det(J))
                for a in range(8):
                    fe[3 * a: 3 * a + 3] += N[a] * rho * g * detJ
    return fe



def _build_element_dof_map(elements: np.ndarray) -> np.ndarray:
    elems = np.asarray(elements, dtype=np.int64)
    edofs = np.empty((elems.shape[0], 24), dtype=np.int64)
    for a in range(8):
        base = 3 * elems[:, a]
        edofs[:, 3 * a + 0] = base + 0
        edofs[:, 3 * a + 1] = base + 1
        edofs[:, 3 * a + 2] = base + 2
    return edofs



def _canonical_element_signature(coords: np.ndarray, decimals: int = 10) -> tuple[float, ...]:
    rel = np.asarray(coords, dtype=float) - np.min(coords, axis=0, keepdims=True)
    return tuple(np.round(rel.reshape(-1), decimals=decimals).tolist())



def extract_hex8_submesh(grid: pv.UnstructuredGrid) -> Hex8Submesh:
    hex_cell_ids = []
    connectivity = []
    voxel_reorder = np.array([0, 1, 3, 2, 4, 5, 7, 6], dtype=np.int64)
    for cid in range(grid.n_cells):
        ctype = int(grid.celltypes[cid])
        if ctype not in {int(pv.CellType.HEXAHEDRON), int(pv.CellType.VOXEL)}:
            continue
        cell = grid.get_cell(cid)
        pids = np.asarray(cell.point_ids, dtype=np.int64)
        if pids.size != 8:
            continue
        if ctype == int(pv.CellType.VOXEL):
            pids = pids[voxel_reorder]
        hex_cell_ids.append(cid)
        connectivity.append(pids)
    if not connectivity:
        return Hex8Submesh(
            global_point_ids=np.empty((0,), dtype=np.int64),
            points=np.empty((0, 3), dtype=float),
            elements=np.empty((0, 8), dtype=np.int64),
            full_cell_ids=np.empty((0,), dtype=np.int64),
            local_by_global={},
        )
    conn = np.asarray(connectivity, dtype=np.int64)
    unique_pids = np.unique(conn.reshape(-1))
    local_conn = np.searchsorted(unique_pids, conn)
    local_by_global = {int(g): i for i, g in enumerate(unique_pids.tolist())}
    return Hex8Submesh(
        global_point_ids=unique_pids,
        points=np.asarray(grid.points[unique_pids], dtype=float),
        elements=np.asarray(local_conn, dtype=np.int64),
        full_cell_ids=np.asarray(hex_cell_ids, dtype=np.int64),
        local_by_global=local_by_global,
    )



def subset_hex8_submesh(base: Hex8Submesh, mask: np.ndarray) -> Hex8Submesh:
    elems = np.asarray(base.elements[mask], dtype=np.int64)
    full_ids = np.asarray(base.full_cell_ids[mask], dtype=np.int64)
    if elems.size == 0:
        return Hex8Submesh(
            global_point_ids=np.empty((0,), dtype=np.int64),
            points=np.empty((0, 3), dtype=float),
            elements=np.empty((0, 8), dtype=np.int64),
            full_cell_ids=np.empty((0,), dtype=np.int64),
            local_by_global={},
        )
    used_local = np.unique(elems.reshape(-1))
    new_elems = np.searchsorted(used_local, elems)
    new_points = np.asarray(base.points[used_local], dtype=float)
    new_global = np.asarray(base.global_point_ids[used_local], dtype=np.int64)
    local_by_global = {int(g): i for i, g in enumerate(new_global.tolist())}
    return Hex8Submesh(
        global_point_ids=new_global,
        points=new_points,
        elements=np.asarray(new_elems, dtype=np.int64),
        full_cell_ids=full_ids,
        local_by_global=local_by_global,
    )



def select_bc_nodes(points: np.ndarray, bc: BoundaryCondition, tol: float = 1e-8) -> np.ndarray:
    target = bc.target.lower()
    if target == "all":
        return np.arange(points.shape[0], dtype=np.int64)
    axes = {
        "xmin": (0, np.min(points[:, 0])), "xmax": (0, np.max(points[:, 0])),
        "ymin": (1, np.min(points[:, 1])), "ymax": (1, np.max(points[:, 1])),
        "zmin": (2, np.min(points[:, 2])), "zmax": (2, np.max(points[:, 2])),
    }
    if target in axes:
        ax, val = axes[target]
        return np.where(np.isclose(points[:, ax], val, atol=tol))[0]
    return np.asarray(bc.metadata.get("point_ids", []), dtype=np.int64)



def apply_stage_nodal_loads(F: np.ndarray, points: np.ndarray, loads: tuple[LoadDefinition, ...]) -> None:
    for load in loads:
        if load.kind.lower() != "point_force":
            continue
        target = load.target.lower()
        if target == "all":
            node_ids = np.arange(points.shape[0], dtype=np.int64)
        else:
            node_ids = np.asarray(load.metadata.get("point_ids", []), dtype=np.int64)
        if node_ids.size == 0:
            continue
        value = np.asarray(load.values, dtype=float)[:3]
        for comp in range(min(3, value.size)):
            np.add.at(F, 3 * node_ids + comp, float(value[comp]))



def solve_linear_hex8(
    submesh: Hex8Submesh,
    cell_materials: list[LinearRegionMaterial],
    bcs: tuple[BoundaryCondition, ...],
    loads: tuple[LoadDefinition, ...],
    gravity: tuple[float, float, float],
    displacement_scale: float = 1.0,
    prefer_sparse: bool = True,
    thread_count: int = 0,
    compute_device: str = 'cpu',
    solver_metadata: dict[str, object] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object]]:
    n_nodes = submesh.points.shape[0]
    ndof = n_nodes * 3
    if n_nodes == 0:
        return np.empty((0, 3)), np.empty((0, 6)), np.empty((0,))

    sp = _optional_import('scipy.sparse')
    sparse_ok = bool(prefer_sparse and sp is not None and ndof >= 900)
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
        'backend': 'cpu-element-loop',
        'device': str(compute_device),
        'warnings': [],
        'used_warp': False,
    }

    warp_cfg = resolve_warp_hex8_config(solver_metadata)
    warp_K = warp_F = None
    if sparse_ok:
        warp_K, warp_F, warp_info = try_warp_hex8_linear_assembly(
            submesh.points,
            submesh.elements,
            np.asarray([float(m.E) for m in cell_materials], dtype=float),
            np.asarray([float(m.nu) for m in cell_materials], dtype=float),
            np.asarray([float(m.rho) for m in cell_materials], dtype=float),
            gravity,
            ndof=ndof,
            requested_device=str(compute_device),
            config=warp_cfg,
            block_pattern=build_block_sparse_pattern(submesh.elements),
        )
        assembly_info.update({
            'backend': str(warp_info.backend),
            'device': str(warp_info.device),
            'used_warp': bool(warp_info.used),
            'precision': str(warp_info.precision),
            'element_count': int(warp_info.element_count),
        })
        if warp_info.warnings:
            assembly_info['warnings'] = list(warp_info.warnings)
        if warp_K is not None and warp_F is not None:
            K = warp_K
            F = np.asarray(warp_F, dtype=float)

    if warp_K is None or warp_F is None:
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
                Ke = element_stiffness_hex8(coords, D)
                fe = element_body_force_hex8(coords, mat.rho, gravity)
                B0, _, _ = bmatrix_hex8(coords, 0.0, 0.0, 0.0)
                response_cache[cache_key] = (Ke, fe, B0)
            else:
                Ke, fe, B0 = cached

            if sparse_ok:
                row_parts.append(np.repeat(edofs, 24))
                col_parts.append(np.tile(edofs, 24))
                data_parts.append(np.asarray(Ke, dtype=float).reshape(-1))
            else:
                K[np.ix_(edofs, edofs)] += Ke
            F[edofs] += fe
            geom_cache[shape_key] = {'B0': B0, 'D': D}

    if (warp_K is None or warp_F is None) and sparse_ok:
        rows = np.concatenate(row_parts) if row_parts else np.empty((0,), dtype=np.int64)
        cols = np.concatenate(col_parts) if col_parts else np.empty((0,), dtype=np.int64)
        data = np.concatenate(data_parts) if data_parts else np.empty((0,), dtype=float)
        K = sp.coo_matrix((data, (rows, cols)), shape=(ndof, ndof)).tocsr()

    apply_stage_nodal_loads(F, submesh.points, loads)

    fixed_dofs: list[int] = []
    fixed_values: list[float] = []
    for bc in bcs:
        if bc.kind.lower() != "displacement":
            continue
        node_ids = select_bc_nodes(submesh.points, bc)
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
            nid = int(zmin_nodes[0])
            fixed_dofs_arr = np.array([3 * nid, 3 * nid + 1, 3 * nid + 2], dtype=np.int64)
            fixed_values_arr = np.zeros(3, dtype=float)

    all_dofs = np.arange(ndof, dtype=np.int64)
    free = np.setdiff1d(all_dofs, fixed_dofs_arr)
    u = np.zeros(ndof, dtype=float)
    if free.size:
        linear_context = LinearSolverContext()
        solver_meta = dict(solver_metadata or {})
        solver_meta.setdefault('block_size', 3)
        solver_meta.setdefault('preconditioner', 'block-jacobi')
        solver_meta.setdefault('ordering', 'rcm')
        solver_meta.setdefault('warp_full_gpu_linear_solve', str(compute_device).lower().startswith('cuda'))
        if hasattr(K, 'to_csr') and bool(solver_meta.get('warp_full_gpu_linear_solve', False)):
            try:
                u, solve_info = solve_linear_system(
                    K,
                    F,
                    prefer_sparse=prefer_sparse,
                    thread_count=thread_count,
                    assume_symmetric=True,
                    context=linear_context,
                    metadata=solver_meta,
                    block_size=3,
                    compute_device=compute_device,
                    fixed_dofs=fixed_dofs_arr,
                    fixed_values=fixed_values_arr,
                )
                u = np.asarray(u, dtype=float).reshape(-1)
                if u.size != ndof:
                    raise ValueError(f'full-system solve returned size {u.size}, expected {ndof}')
            except Exception as exc:
                assembly_info.setdefault('warnings', []).append(f'GPU full-system linear solve fallback: {exc}')
                solver_meta = dict(solver_meta)
                solver_meta['warp_full_gpu_linear_solve'] = False
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
                    compute_device=compute_device,
                )
        else:
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
                compute_device=compute_device,
            )
        assembly_info['linear_solver'] = solve_info.backend
        assembly_info['linear_ordering'] = solve_info.ordering
        assembly_info['linear_preconditioner'] = solve_info.preconditioner
        assembly_info['linear_device'] = solve_info.device
        if solve_info.warnings:
            assembly_info.setdefault('warnings', []).extend(list(solve_info.warnings))
    if fixed_dofs_arr.size:
        u[fixed_dofs_arr] = fixed_values_arr

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
    return u_nodes, cell_stresses, vm, assembly_info



def von_mises(stress6: np.ndarray) -> np.ndarray:
    s = np.asarray(stress6, dtype=float)
    sx, sy, sz, txy, tyz, txz = s.T
    return np.sqrt(np.maximum(0.0, 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy**2 + tyz**2 + txz**2)))
