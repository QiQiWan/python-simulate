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

from geoai_simkit.core.model import BoundaryCondition, LoadDefinition, SimulationModel
from geoai_simkit.solver.linear_algebra import solve_linear_system


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
    local_by_global = {int(g): i for i, g in enumerate(unique_pids.tolist())}
    local_conn = np.vectorize(lambda g: local_by_global[int(g)], otypes=[np.int64])(conn)
    return Hex8Submesh(
        global_point_ids=unique_pids,
        points=np.asarray(grid.points[unique_pids], dtype=float),
        elements=local_conn,
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
    map_old_to_new = {int(old): i for i, old in enumerate(used_local.tolist())}
    new_elems = np.vectorize(lambda x: map_old_to_new[int(x)], otypes=[np.int64])(elems)
    new_points = np.asarray(base.points[used_local], dtype=float)
    new_global = np.asarray(base.global_point_ids[used_local], dtype=np.int64)
    local_by_global = {int(g): i for i, g in enumerate(new_global.tolist())}
    return Hex8Submesh(
        global_point_ids=new_global,
        points=new_points,
        elements=new_elems,
        full_cell_ids=full_ids,
        local_by_global=local_by_global,
    )
def select_bc_nodes(points: np.ndarray, bc: BoundaryCondition, tol: float = 1e-8) -> np.ndarray:
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    target = bc.target.lower()
    if target in {"bottom", "zmin"}:
        return np.where(np.isclose(z, z.min(), atol=tol))[0]
    if target == "zmax" or target == "top":
        return np.where(np.isclose(z, z.max(), atol=tol))[0]
    if target == "xmin":
        return np.where(np.isclose(x, x.min(), atol=tol))[0]
    if target == "xmax":
        return np.where(np.isclose(x, x.max(), atol=tol))[0]
    if target == "ymin":
        return np.where(np.isclose(y, y.min(), atol=tol))[0]
    if target == "ymax":
        return np.where(np.isclose(y, y.max(), atol=tol))[0]
    if target == "all":
        return np.arange(points.shape[0], dtype=np.int64)
    point_ids = bc.metadata.get("point_ids")
    if point_ids is not None:
        return np.asarray(point_ids, dtype=np.int64)
    return np.empty((0,), dtype=np.int64)


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
        value = np.asarray(load.values, dtype=float)
        for nid in node_ids:
            F[3 * nid: 3 * nid + 3] += value


def solve_linear_hex8(
    submesh: Hex8Submesh,
    cell_materials: list[LinearRegionMaterial],
    bcs: tuple[BoundaryCondition, ...],
    loads: tuple[LoadDefinition, ...],
    gravity: tuple[float, float, float],
    displacement_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_nodes = submesh.points.shape[0]
    ndof = n_nodes * 3
    if n_nodes == 0:
        return np.empty((0, 3)), np.empty((0, 6)), np.empty((0,))
    K = np.zeros((ndof, ndof), dtype=float)
    F = np.zeros(ndof, dtype=float)
    cell_stresses = np.zeros((submesh.elements.shape[0], 6), dtype=float)

    for eidx, elem in enumerate(submesh.elements):
        coords = submesh.points[elem]
        mat = cell_materials[eidx]
        D = isotropic_D(mat.E, mat.nu)
        Ke = element_stiffness_hex8(coords, D)
        fe = element_body_force_hex8(coords, mat.rho, gravity)
        edofs = np.zeros(24, dtype=np.int64)
        for a, nid in enumerate(elem):
            edofs[3 * a: 3 * a + 3] = [3 * nid, 3 * nid + 1, 3 * nid + 2]
        K[np.ix_(edofs, edofs)] += Ke
        F[edofs] += fe

    apply_stage_nodal_loads(F, submesh.points, loads)

    fixed_dofs = []
    fixed_values = []
    for bc in bcs:
        if bc.kind.lower() != "displacement":
            continue
        node_ids = select_bc_nodes(submesh.points, bc)
        vals = np.asarray(bc.values, dtype=float)
        for nid in node_ids:
            for comp in bc.components:
                fixed_dofs.append(3 * nid + comp)
                fixed_values.append(vals[min(comp, len(vals) - 1)])
    fixed_dofs = np.asarray(fixed_dofs, dtype=np.int64)
    fixed_values = np.asarray(fixed_values, dtype=float)
    if fixed_dofs.size == 0:
        # prevent rigid body singularity by fixing bottom-z if nothing specified
        zmin_nodes = np.where(np.isclose(submesh.points[:, 2], submesh.points[:, 2].min()))[0]
        for nid in zmin_nodes[:1]:
            fixed_dofs = np.concatenate([fixed_dofs, np.array([3*nid, 3*nid+1, 3*nid+2], dtype=np.int64)])
            fixed_values = np.concatenate([fixed_values, np.zeros(3)])

    all_dofs = np.arange(ndof, dtype=np.int64)
    free = np.setdiff1d(all_dofs, fixed_dofs)
    u = np.zeros(ndof, dtype=float)
    if free.size:
        F_eff = F[free].copy()
        if fixed_dofs.size:
            F_eff -= K[np.ix_(free, fixed_dofs)] @ fixed_values
        Kff = K[np.ix_(free, free)]
        u[free], _ = solve_linear_system(Kff, F_eff, prefer_sparse=True)
    if fixed_dofs.size:
        u[fixed_dofs] = fixed_values

    u_nodes = u.reshape(n_nodes, 3)
    for eidx, elem in enumerate(submesh.elements):
        coords = submesh.points[elem]
        mat = cell_materials[eidx]
        D = isotropic_D(mat.E, mat.nu)
        edofs = np.zeros(24, dtype=np.int64)
        for a, nid in enumerate(elem):
            edofs[3 * a: 3 * a + 3] = [3 * nid, 3 * nid + 1, 3 * nid + 2]
        ue = u[edofs]
        B, _, _ = bmatrix_hex8(coords, 0.0, 0.0, 0.0)
        strain = B @ ue
        cell_stresses[eidx] = D @ strain

    u_nodes *= displacement_scale
    vm = von_mises(cell_stresses)
    return u_nodes, cell_stresses, vm


def von_mises(stress6: np.ndarray) -> np.ndarray:
    s = np.asarray(stress6, dtype=float)
    sx, sy, sz, txy, tyz, txz = s.T
    return np.sqrt(np.maximum(0.0, 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy**2 + tyz**2 + txz**2)))
