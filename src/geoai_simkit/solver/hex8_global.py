from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .base import SolverResult, SolverSettings
from .linalg import constrained_residual_norm, solve_linear_system


@dataclass(slots=True)
class Hex8Submesh:
    points: np.ndarray
    cells: np.ndarray
    metadata: dict | None = None


def structured_hex_box(nx: int = 1, ny: int = 1, nz: int = 1, size: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> Hex8Submesh:
    lx, ly, lz = map(float, size)
    pts: list[list[float]] = []
    node_id: dict[tuple[int, int, int], int] = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                node_id[(i, j, k)] = len(pts)
                pts.append([lx * i / nx, ly * j / ny, lz * k / nz])
    cells: list[list[int]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                cells.append([
                    node_id[(i, j, k)], node_id[(i + 1, j, k)], node_id[(i + 1, j + 1, k)], node_id[(i, j + 1, k)],
                    node_id[(i, j, k + 1)], node_id[(i + 1, j, k + 1)], node_id[(i + 1, j + 1, k + 1)], node_id[(i, j + 1, k + 1)],
                ])
    return Hex8Submesh(np.asarray(pts, dtype=float), np.asarray(cells, dtype=int), {"nx": nx, "ny": ny, "nz": nz, "size": size})


def elastic_matrix(E: float, nu: float) -> np.ndarray:
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


def _shape_derivatives_nat(xi: float, eta: float, zeta: float) -> np.ndarray:
    signs = np.array([
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
    ], dtype=float)
    dN = np.zeros((8, 3), dtype=float)
    for a, (sx, sy, sz) in enumerate(signs):
        dN[a, 0] = 0.125 * sx * (1 + sy * eta) * (1 + sz * zeta)
        dN[a, 1] = 0.125 * sy * (1 + sx * xi) * (1 + sz * zeta)
        dN[a, 2] = 0.125 * sz * (1 + sx * xi) * (1 + sy * eta)
    return dN


def bmatrix_hex8(coords: np.ndarray, xi: float, eta: float, zeta: float) -> tuple[np.ndarray, float]:
    coords = np.asarray(coords, dtype=float).reshape(8, 3)
    dN_nat = _shape_derivatives_nat(xi, eta, zeta)
    J = dN_nat.T @ coords
    detJ = float(np.linalg.det(J))
    if detJ <= 0:
        raise ValueError(f"Hex8 element has non-positive Jacobian det={detJ}")
    dN_xyz = dN_nat @ np.linalg.inv(J)
    B = np.zeros((6, 24), dtype=float)
    for a in range(8):
        ix = 3 * a
        dx, dy, dz = dN_xyz[a]
        B[0, ix] = dx
        B[1, ix + 1] = dy
        B[2, ix + 2] = dz
        B[3, ix] = dy
        B[3, ix + 1] = dx
        B[4, ix + 1] = dz
        B[4, ix + 2] = dy
        B[5, ix] = dz
        B[5, ix + 2] = dx
    return B, detJ


def element_stiffness_hex8(coords: np.ndarray, D: np.ndarray) -> np.ndarray:
    gp = 1.0 / np.sqrt(3.0)
    Ke = np.zeros((24, 24), dtype=float)
    for xi in (-gp, gp):
        for eta in (-gp, gp):
            for zeta in (-gp, gp):
                B, detJ = bmatrix_hex8(coords, xi, eta, zeta)
                Ke += B.T @ D @ B * detJ
    return 0.5 * (Ke + Ke.T)


def assemble_hex8_global(mesh: Hex8Submesh, D: np.ndarray | Callable[[int], np.ndarray]) -> np.ndarray:
    ndof = mesh.points.shape[0] * 3
    K = np.zeros((ndof, ndof), dtype=float)
    for eid, cell in enumerate(mesh.cells):
        De = D(eid) if callable(D) else D
        Ke = element_stiffness_hex8(mesh.points[cell], De)
        dofs = np.array([3 * n + c for n in cell for c in range(3)], dtype=int)
        K[np.ix_(dofs, dofs)] += Ke
    return 0.5 * (K + K.T)


def solve_linear_hex8(mesh: Hex8Submesh, E: float, nu: float, loads: dict[int, float] | None = None, fixed_dofs: dict[int, float] | None = None) -> SolverResult:
    D = elastic_matrix(E, nu)
    K = assemble_hex8_global(mesh, D)
    f = np.zeros(mesh.points.shape[0] * 3, dtype=float)
    for dof, value in (loads or {}).items():
        f[int(dof)] += float(value)
    fixed = dict(fixed_dofs or {})
    u = solve_linear_system(K, f, fixed)
    rn = constrained_residual_norm(K, u, f, fixed)
    return SolverResult(converged=rn < 1e-6, displacement=u, residual_norm=rn, iterations=1, status="hex8-linear", metadata={"K": K, "f": f})


def affine_displacement(point: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(point, dtype=float)
    return np.array([0.01 * x + 0.002 * y, -0.003 * x + 0.004 * y + 0.001 * z, 0.002 * x - 0.001 * y + 0.005 * z], dtype=float)


def run_hex8_global_patch_solve_benchmark() -> dict:
    mesh = structured_hex_box(2, 1, 1)
    E, nu = 25e6, 0.28
    fixed = {3 * i + c: float(affine_displacement(p)[c]) for i, p in enumerate(mesh.points) for c in range(3)}
    result = solve_linear_hex8(mesh, E, nu, fixed_dofs=fixed)
    D = elastic_matrix(E, nu)
    expected_strain = np.array([0.01, 0.004, 0.005, -0.001, 0.0, 0.004], dtype=float)
    expected_stress = D @ expected_strain
    max_strain_error = 0.0
    max_stress_error = 0.0
    for cell in mesh.cells:
        B, _ = bmatrix_hex8(mesh.points[cell], 0.0, 0.0, 0.0)
        ue = np.array([result.displacement[3 * n + c] for n in cell for c in range(3)], dtype=float)
        strain = B @ ue
        stress = D @ strain
        max_strain_error = max(max_strain_error, float(np.linalg.norm(strain - expected_strain)))
        max_stress_error = max(max_stress_error, float(np.linalg.norm(stress - expected_stress)))
    passed = bool(result.converged and max_strain_error < 1e-10 and max_stress_error < 1e-3)
    return {"name": "hex8_global_patch_solve", "passed": passed, "max_strain_error": max_strain_error, "max_stress_error": max_stress_error, "residual_norm": result.residual_norm}


def solve_nonlinear_hex8(
    mesh: Hex8Submesh,
    material,
    load_steps: list[dict[int, float]],
    fixed_dofs: dict[int, float],
    settings: SolverSettings | None = None,
) -> SolverResult:
    settings = settings or SolverSettings()
    ndof = mesh.points.shape[0] * 3
    u = np.zeros(ndof, dtype=float)
    states = [material.create_state() for _ in range(len(mesh.cells))]
    history: list[dict] = []
    converged = True
    for step_id, loads in enumerate(load_steps, start=1):
        f = np.zeros(ndof, dtype=float)
        for dof, value in loads.items():
            f[int(dof)] += float(value)
        step_converged = False
        for it in range(int(settings.max_iterations)):
            def tangent_for(eid: int):
                if hasattr(material, "consistent_tangent_matrix"):
                    return material.consistent_tangent_matrix(states[eid])
                return material.tangent_matrix(states[eid])
            K = assemble_hex8_global(mesh, tangent_for)
            du = solve_linear_system(K, f - K @ u, fixed_dofs={k: 0.0 for k in fixed_dofs})
            u += du
            rn = constrained_residual_norm(K, u, f, fixed_dofs)
            history.append({"step": step_id, "iteration": it + 1, "residual_norm": float(rn), "increment_norm": float(np.linalg.norm(du))})
            if rn < settings.tolerance or np.linalg.norm(du) < settings.tolerance:
                step_converged = True
                break
        if not step_converged:
            converged = False
        # update one effective strain per element at the center, enough for benchmark state propagation
        for eid, cell in enumerate(mesh.cells):
            B, _ = bmatrix_hex8(mesh.points[cell], 0.0, 0.0, 0.0)
            ue = np.array([u[3 * n + c] for n in cell for c in range(3)], dtype=float)
            total_strain = B @ ue
            prev = np.asarray(states[eid].strain, dtype=float)
            states[eid] = material.update(total_strain - prev, states[eid])
    return SolverResult(converged=converged, displacement=u, residual_norm=float(history[-1]["residual_norm"] if history else 0.0), iterations=len(history), status="hex8-nonlinear", metadata={"history": history, "states": states})


def run_hex8_nonlinear_global_solve_benchmark() -> dict:
    from geoai_simkit.materials.mohr_coulomb import MohrCoulomb

    mesh = structured_hex_box(1, 1, 1)
    mat = MohrCoulomb(E=30e6, nu=0.30, cohesion=60e3, friction_deg=30.0, dilation_deg=5.0, tensile_strength=10e3)
    left_nodes = [i for i, p in enumerate(mesh.points) if abs(p[0]) < 1e-12]
    right_nodes = [i for i, p in enumerate(mesh.points) if abs(p[0] - 1.0) < 1e-12]
    fixed = {3 * n + c: 0.0 for n in left_nodes for c in range(3)}
    steps: list[dict[int, float]] = []
    for scale in (0.25, 0.5, 0.75, 1.0):
        loads: dict[int, float] = {}
        for n in right_nodes:
            loads[3 * n] = -2.0e3 * scale / len(right_nodes)
        steps.append(loads)
    res = solve_nonlinear_hex8(mesh, mat, steps, fixed, SolverSettings(max_iterations=12, tolerance=1e-7))
    yielded = any(bool(s.internal.get("yielded", False)) for s in res.metadata.get("states", []))
    return {"name": "hex8_nonlinear_global_solve", "passed": bool(res.converged and np.isfinite(res.residual_norm)), "converged": res.converged, "iterations": res.iterations, "residual_norm": res.residual_norm, "yielded": yielded}
