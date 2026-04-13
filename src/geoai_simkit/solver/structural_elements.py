from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoai_simkit.core.model import LoadDefinition, StructuralElementDefinition
from geoai_simkit.solver.hex8_linear import Hex8Submesh


@dataclass(slots=True)
class StructuralDofMap:
    trans_ndof: int
    total_ndof: int
    rot_base: int
    rot_by_local_node: dict[int, int] = field(default_factory=dict)

    def has_rotation(self, local_node: int) -> bool:
        return int(local_node) in self.rot_by_local_node

    def rot_dofs(self, local_node: int) -> np.ndarray:
        base = self.rot_by_local_node[int(local_node)]
        return np.array([base, base + 1, base + 2], dtype=np.int64)

    def structural_rotation_field(self, n_local_nodes: int, solution: np.ndarray) -> np.ndarray:
        rot = np.zeros((n_local_nodes, 3), dtype=float)
        for nid, base in self.rot_by_local_node.items():
            rot[int(nid)] = solution[base:base + 3]
        return rot


@dataclass(slots=True)
class StructuralAssemblyResult:
    K: np.ndarray
    F: np.ndarray
    count: int
    warnings: list[str]
    dof_map: StructuralDofMap


def build_structural_dof_map(structures: list[StructuralElementDefinition], submesh: Hex8Submesh) -> StructuralDofMap:
    trans_ndof = submesh.points.shape[0] * 3
    rot_nodes: set[int] = set()
    for item in structures:
        kind = item.kind.lower()
        if kind in {"beam2", "frame3d", "shellquad4"}:
            for g in item.point_ids:
                if int(g) in submesh.local_by_global:
                    rot_nodes.add(submesh.local_by_global[int(g)])
    rot_by_local_node: dict[int, int] = {}
    cursor = trans_ndof
    for nid in sorted(rot_nodes):
        rot_by_local_node[int(nid)] = cursor
        cursor += 3
    return StructuralDofMap(
        trans_ndof=trans_ndof,
        total_ndof=cursor,
        rot_base=trans_ndof,
        rot_by_local_node=rot_by_local_node,
    )


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        raise ValueError("Zero-length vector encountered while building structural element frame")
    return v / n


def _local_frame(p0: np.ndarray, p1: np.ndarray, up_hint: np.ndarray | None = None) -> np.ndarray:
    ex = _unit(p1 - p0)
    if up_hint is None:
        up_hint = np.array([0.0, 0.0, 1.0], dtype=float)
        if abs(float(np.dot(up_hint, ex))) > 0.9:
            up_hint = np.array([0.0, 1.0, 0.0], dtype=float)
    ey = up_hint - np.dot(up_hint, ex) * ex
    if np.linalg.norm(ey) < 1e-12:
        up_hint = np.array([0.0, 1.0, 0.0], dtype=float)
        ey = up_hint - np.dot(up_hint, ex) * ex
    ey = _unit(ey)
    ez = _unit(np.cross(ex, ey))
    ey = _unit(np.cross(ez, ex))
    return np.column_stack([ex, ey, ez])


def truss2_stiffness(p0: np.ndarray, p1: np.ndarray, E: float, A: float) -> np.ndarray:
    L = float(np.linalg.norm(p1 - p0))
    n = _unit(p1 - p0)
    k = E * A / max(L, 1e-12)
    P = np.outer(n, n)
    return np.block([[P, -P], [-P, P]]) * k


def frame3d_local_stiffness(E: float, G: float, A: float, Iy: float, Iz: float, J: float, L: float) -> np.ndarray:
    L = max(float(L), 1e-12)
    k = np.zeros((12, 12), dtype=float)
    EA = E * A / L
    GJ = G * J / L
    EIz = E * Iz
    EIy = E * Iy

    # axial
    k[0, 0] = k[6, 6] = EA
    k[0, 6] = k[6, 0] = -EA
    # torsion
    k[3, 3] = k[9, 9] = GJ
    k[3, 9] = k[9, 3] = -GJ

    # bending about local z -> v / ry
    kbz = np.array([
        [12 * EIz / L**3, 6 * EIz / L**2, -12 * EIz / L**3, 6 * EIz / L**2],
        [6 * EIz / L**2, 4 * EIz / L, -6 * EIz / L**2, 2 * EIz / L],
        [-12 * EIz / L**3, -6 * EIz / L**2, 12 * EIz / L**3, -6 * EIz / L**2],
        [6 * EIz / L**2, 2 * EIz / L, -6 * EIz / L**2, 4 * EIz / L],
    ], dtype=float)
    idx = [1, 5, 7, 11]
    for i in range(4):
        for j in range(4):
            k[idx[i], idx[j]] += kbz[i, j]

    # bending about local y -> w / rz
    kby = np.array([
        [12 * EIy / L**3, -6 * EIy / L**2, -12 * EIy / L**3, -6 * EIy / L**2],
        [-6 * EIy / L**2, 4 * EIy / L, 6 * EIy / L**2, 2 * EIy / L],
        [-12 * EIy / L**3, 6 * EIy / L**2, 12 * EIy / L**3, 6 * EIy / L**2],
        [-6 * EIy / L**2, 2 * EIy / L, 6 * EIy / L**2, 4 * EIy / L],
    ], dtype=float)
    idx = [2, 4, 8, 10]
    for i in range(4):
        for j in range(4):
            k[idx[i], idx[j]] += kby[i, j]
    return k


def frame3d_stiffness(
    p0: np.ndarray,
    p1: np.ndarray,
    E: float,
    A: float,
    Iy: float,
    Iz: float,
    J: float,
    nu: float = 0.3,
    G: float | None = None,
    up_hint: np.ndarray | None = None,
) -> np.ndarray:
    L = float(np.linalg.norm(p1 - p0))
    Q = _local_frame(p0, p1, up_hint=up_hint)
    R = Q.T
    if G is None:
        G = E / (2.0 * (1.0 + nu))
    Kloc = frame3d_local_stiffness(E, G, A, Iy, Iz, J, L)
    T = np.zeros((12, 12), dtype=float)
    for i in range(4):
        T[3 * i:3 * i + 3, 3 * i:3 * i + 3] = R
    return T.T @ Kloc @ T


def _quad_shape(xi: float, eta: float) -> tuple[np.ndarray, np.ndarray]:
    N = 0.25 * np.array([
        (1 - xi) * (1 - eta),
        (1 + xi) * (1 - eta),
        (1 + xi) * (1 + eta),
        (1 - xi) * (1 + eta),
    ], dtype=float)
    dN = 0.25 * np.array([
        [-(1 - eta), -(1 - xi)],
        [+(1 - eta), -(1 + xi)],
        [+(1 + eta), +(1 + xi)],
        [-(1 + eta), +(1 - xi)],
    ], dtype=float)
    return N, dN


def _quad_jacobian(xy: np.ndarray, dN_dxi: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    J = xy.T @ dN_dxi
    detJ = float(np.linalg.det(J))
    if abs(detJ) < 1e-12:
        raise ValueError("Degenerate shell quadrilateral encountered")
    invJ = np.linalg.inv(J)
    dN_dx = dN_dxi @ invJ.T
    return J, detJ, dN_dx


def shellquad4_stiffness(
    coords4: np.ndarray,
    E: float,
    nu: float,
    thickness: float,
    shear_factor: float = 5.0 / 6.0,
    drilling_penalty: float = 1.0e-4,
) -> np.ndarray:
    x0 = coords4[0]
    e1 = _unit(coords4[1] - coords4[0])
    n = np.cross(coords4[1] - coords4[0], coords4[3] - coords4[0])
    if np.linalg.norm(n) < 1e-12:
        n = np.cross(coords4[2] - coords4[0], coords4[3] - coords4[0])
    e3 = _unit(n)
    e2 = _unit(np.cross(e3, e1))
    Q = np.column_stack([e1, e2, e3])
    R = Q.T
    xy = np.zeros((4, 2), dtype=float)
    for i, p in enumerate(coords4):
        q = R @ (p - x0)
        xy[i] = q[:2]

    # membrane contribution on local [u,v]
    fac = E / max(1e-12, (1.0 - nu**2))
    Dm = fac * np.array([[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, 0.5 * (1.0 - nu)]], dtype=float)
    Kloc = np.zeros((24, 24), dtype=float)
    gps = (-1.0 / np.sqrt(3.0), 1.0 / np.sqrt(3.0))
    for xi in gps:
        for eta in gps:
            N, dN_dxi = _quad_shape(xi, eta)
            _, detJ, dN_dx = _quad_jacobian(xy, dN_dxi)
            Bm = np.zeros((3, 8), dtype=float)
            for a in range(4):
                Bm[0, 2 * a] = dN_dx[a, 0]
                Bm[1, 2 * a + 1] = dN_dx[a, 1]
                Bm[2, 2 * a] = dN_dx[a, 1]
                Bm[2, 2 * a + 1] = dN_dx[a, 0]
            Km2 = thickness * detJ * (Bm.T @ Dm @ Bm)
            map_uv = []
            for a in range(4):
                map_uv.extend([6 * a + 0, 6 * a + 1])
            map_uv = np.asarray(map_uv, dtype=np.int64)
            Kloc[np.ix_(map_uv, map_uv)] += Km2

    # Mindlin plate bending + shear on local [w, rx, ry]
    Db = E * thickness**3 / (12.0 * max(1e-12, 1.0 - nu**2)) * np.array(
        [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, 0.5 * (1.0 - nu)]], dtype=float
    )
    G = E / (2.0 * (1.0 + nu))
    Ds = shear_factor * G * thickness * np.eye(2, dtype=float)
    # bending part 2x2 integration
    for xi in gps:
        for eta in gps:
            N, dN_dxi = _quad_shape(xi, eta)
            _, detJ, dN_dx = _quad_jacobian(xy, dN_dxi)
            Bb = np.zeros((3, 12), dtype=float)
            Bs = np.zeros((2, 12), dtype=float)
            for a in range(4):
                i = 3 * a
                # [w, rx, ry] local DOFs
                Bb[0, i + 1] = dN_dx[a, 0]          # kxx = drx/dx
                Bb[1, i + 2] = dN_dx[a, 1]          # kyy = dry/dy
                Bb[2, i + 1] = dN_dx[a, 1]          # kxy = drx/dy + dry/dx
                Bb[2, i + 2] = dN_dx[a, 0]
                Bs[0, i + 0] = dN_dx[a, 0]          # gamma_xz = dw/dx - rx
                Bs[0, i + 1] = -N[a]
                Bs[1, i + 0] = dN_dx[a, 1]          # gamma_yz = dw/dy - ry
                Bs[1, i + 2] = -N[a]
            Kb3 = detJ * (Bb.T @ Db @ Bb)
            map_wrr = []
            for a in range(4):
                map_wrr.extend([6 * a + 2, 6 * a + 3, 6 * a + 4])
            map_wrr = np.asarray(map_wrr, dtype=np.int64)
            Kloc[np.ix_(map_wrr, map_wrr)] += Kb3
    # shear reduced integration at center
    N0, dN0 = _quad_shape(0.0, 0.0)
    _, detJ0, dN_dx0 = _quad_jacobian(xy, dN0)
    Bs = np.zeros((2, 12), dtype=float)
    for a in range(4):
        i = 3 * a
        Bs[0, i + 0] = dN_dx0[a, 0]
        Bs[0, i + 1] = -N0[a]
        Bs[1, i + 0] = dN_dx0[a, 1]
        Bs[1, i + 2] = -N0[a]
    Ks3 = 4.0 * detJ0 * (Bs.T @ Ds @ Bs)
    map_wrr = []
    for a in range(4):
        map_wrr.extend([6 * a + 2, 6 * a + 3, 6 * a + 4])
    map_wrr = np.asarray(map_wrr, dtype=np.int64)
    Kloc[np.ix_(map_wrr, map_wrr)] += Ks3

    # drilling stiffness on local rz
    def _cross2(a: np.ndarray, b: np.ndarray) -> float:
        return float(a[0] * b[1] - a[1] * b[0])
    area = 0.5 * abs(_cross2(xy[1] - xy[0], xy[3] - xy[0])) + 0.5 * abs(_cross2(xy[2] - xy[1], xy[3] - xy[1]))
    kdr = drilling_penalty * E * thickness * max(float(area), 1.0e-9)
    for a in range(4):
        Kloc[6 * a + 5, 6 * a + 5] += kdr

    T = np.zeros((24, 24), dtype=float)
    for a in range(4):
        T[6 * a:6 * a + 3, 6 * a:6 * a + 3] = R
        T[6 * a + 3:6 * a + 6, 6 * a + 3:6 * a + 6] = R
    return T.T @ Kloc @ T


def _trans_dofs(local_node: int) -> np.ndarray:
    base = 3 * int(local_node)
    return np.array([base, base + 1, base + 2], dtype=np.int64)


def _edofs_nodes(local_nodes: list[int], dof_map: StructuralDofMap, rotational: bool) -> np.ndarray:
    edofs: list[int] = []
    for nid in local_nodes:
        edofs.extend(_trans_dofs(nid).tolist())
        if rotational:
            if not dof_map.has_rotation(int(nid)):
                raise KeyError(f"Structural node {nid} requires rotational DOFs but none were allocated")
            edofs.extend(dof_map.rot_dofs(int(nid)).tolist())
    return np.asarray(edofs, dtype=np.int64)


def apply_structural_loads(F: np.ndarray, submesh: Hex8Submesh, dof_map: StructuralDofMap, loads: tuple[LoadDefinition, ...]) -> None:
    for load in loads:
        kind = load.kind.lower()
        point_ids = load.metadata.get("point_ids")
        if point_ids is None:
            continue
        gids = np.asarray(point_ids, dtype=np.int64)
        vals = np.asarray(load.values, dtype=float)
        if kind != "moment":
            continue
        for gid in gids:
            if int(gid) not in submesh.local_by_global:
                continue
            lid = submesh.local_by_global[int(gid)]
            if dof_map.has_rotation(lid):
                F[dof_map.rot_dofs(lid)] += vals[:3]


def assemble_structural_stiffness(
    structures: list[StructuralElementDefinition],
    submesh: Hex8Submesh,
    dof_map: StructuralDofMap | None = None,
) -> StructuralAssemblyResult:
    if dof_map is None:
        dof_map = build_structural_dof_map(structures, submesh)
    ndof = dof_map.total_ndof
    K = np.zeros((ndof, ndof), dtype=float)
    F = np.zeros(ndof, dtype=float)
    count = 0
    warnings: list[str] = []

    for item in structures:
        try:
            local_nodes = [submesh.local_by_global[int(g)] for g in item.point_ids]
        except KeyError:
            warnings.append(f"Structure '{item.name}' skipped because some point IDs are not active in the current submesh")
            continue
        coords = submesh.points[np.asarray(local_nodes, dtype=np.int64)]
        kind = item.kind.lower()
        if kind == "truss2":
            E = float(item.parameters.get("E", 2.1e11))
            A = float(item.parameters.get("A", 1.0e-3))
            Ke = truss2_stiffness(coords[0], coords[1], E, A)
            edofs = np.hstack([_trans_dofs(local_nodes[0]), _trans_dofs(local_nodes[1])])
            K[np.ix_(edofs, edofs)] += Ke
            N0 = float(item.parameters.get("prestress", 0.0))
            if abs(N0) > 0.0:
                n = _unit(coords[1] - coords[0])
                F[edofs] += np.hstack([-N0 * n, N0 * n])
            count += 1
        elif kind in {"beam2", "frame3d"}:
            E = float(item.parameters.get("E", 2.1e11))
            A = float(item.parameters.get("A", 1.0e-3))
            Iy = float(item.parameters.get("Iy", 1.0e-6))
            Iz = float(item.parameters.get("Iz", 1.0e-6))
            J = float(item.parameters.get("J", max(Iy + Iz, 1.0e-8)))
            nu = float(item.parameters.get("nu", 0.3))
            G = item.parameters.get("G")
            if G is not None:
                G = float(G)
            up = np.asarray(item.parameters.get("up", [0.0, 0.0, 1.0]), dtype=float)
            Ke = frame3d_stiffness(coords[0], coords[1], E, A, Iy, Iz, J, nu=nu, G=G, up_hint=up)
            edofs = _edofs_nodes(local_nodes, dof_map, rotational=True)
            K[np.ix_(edofs, edofs)] += Ke
            N0 = float(item.parameters.get("prestress", 0.0))
            if abs(N0) > 0.0:
                n = _unit(coords[1] - coords[0])
                F[edofs[:3]] += -N0 * n
                F[edofs[6:9]] += N0 * n
            count += 1
        elif kind == "shellquad4":
            E = float(item.parameters.get("E", 3.2e10))
            nu = float(item.parameters.get("nu", 0.2))
            t = float(item.parameters.get("thickness", 0.8))
            sf = float(item.parameters.get("shear_factor", 5.0 / 6.0))
            dp = float(item.parameters.get("drilling_penalty", 1.0e-4))
            Ke = shellquad4_stiffness(coords, E, nu, t, shear_factor=sf, drilling_penalty=dp)
            edofs = _edofs_nodes(local_nodes, dof_map, rotational=True)
            K[np.ix_(edofs, edofs)] += Ke
            count += 1
        else:
            warnings.append(f"Unsupported structure kind '{item.kind}' on '{item.name}'")
    return StructuralAssemblyResult(K=K, F=F, count=count, warnings=warnings, dof_map=dof_map)
