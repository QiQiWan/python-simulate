from __future__ import annotations

"""Sparse linear-elastic FEM path for dependency-light verification.

This module is intentionally small, but it is a real end-to-end numerical path:
mesh nodes and cells are assembled into a global sparse stiffness matrix,
Dirichlet constraints are applied, the linear system is solved, and element
strain/stress fields are recovered from the displacement vector.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import warnings

import numpy as np

try:
    from scipy.sparse import coo_matrix, csr_matrix
    from scipy.sparse.linalg import MatrixRankWarning, spsolve
except Exception as exc:  # pragma: no cover - import-time environment guard
    coo_matrix = None  # type: ignore[assignment]
    csr_matrix = None  # type: ignore[assignment]
    MatrixRankWarning = Warning  # type: ignore[assignment]
    spsolve = None  # type: ignore[assignment]
    _SCIPY_IMPORT_ERROR: Exception | None = exc
else:
    _SCIPY_IMPORT_ERROR = None


class _DenseMatrixAdapter:
    """Small matrix adapter used only when scipy is not installed."""

    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = np.asarray(matrix, dtype=float)
        self.shape = self.matrix.shape
        self.nnz = int(np.count_nonzero(np.abs(self.matrix) > 0.0))
        self.backend = "dense_fallback_missing_scipy"

    def __matmul__(self, other: np.ndarray) -> np.ndarray:
        return self.matrix @ other

    def __getitem__(self, key: Any) -> Any:
        return self.matrix[key]


HEX8_TO_TETS: tuple[tuple[int, int, int, int], ...] = (
    (0, 1, 3, 4),
    (1, 2, 3, 6),
    (1, 3, 4, 6),
    (1, 4, 5, 6),
    (3, 4, 6, 7),
)


@dataclass(frozen=True, slots=True)
class LinearElasticMaterial:
    E: float
    nu: float
    unit_weight: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "LinearElasticMaterial":
        data = dict(values or {})
        params = dict(data.get("parameters", {}) or {})
        merged = {**data, **params}
        E = merged.get("E", merged.get("E_ref", merged.get("young_modulus", 1.0)))
        nu = merged.get("nu", merged.get("poisson", 0.0))
        gamma = merged.get("unit_weight", merged.get("gamma", merged.get("gamma_unsat", 0.0)))
        return cls(E=float(E), nu=float(nu), unit_weight=float(gamma))

    def validate(self) -> None:
        if self.E <= 0.0:
            raise ValueError(f"Linear elastic material requires E > 0, got {self.E:g}.")
        if not (0.0 <= self.nu < 0.5):
            raise ValueError(f"Linear elastic material requires 0 <= nu < 0.5, got {self.nu:g}.")

    def stiffness_matrix(self) -> np.ndarray:
        self.validate()
        lam = self.E * self.nu / ((1.0 + self.nu) * (1.0 - 2.0 * self.nu))
        mu = self.E / (2.0 * (1.0 + self.nu))
        return np.array(
            [
                [lam + 2.0 * mu, lam, lam, 0.0, 0.0, 0.0],
                [lam, lam + 2.0 * mu, lam, 0.0, 0.0, 0.0],
                [lam, lam, lam + 2.0 * mu, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, mu, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, mu, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, mu],
            ],
            dtype=float,
        )


@dataclass(slots=True)
class ElementRecovery:
    cell_id: int
    connectivity: tuple[int, ...]
    material_id: str
    volume: float
    strain: np.ndarray
    stress: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": int(self.cell_id),
            "connectivity": [int(v) for v in self.connectivity],
            "material_id": self.material_id,
            "volume": float(self.volume),
            "strain": [float(v) for v in self.strain],
            "stress": [float(v) for v in self.stress],
        }


@dataclass(slots=True)
class SparseLinearStaticResult:
    converged: bool
    displacement: np.ndarray
    residual_norm: float
    relative_residual_norm: float
    status: str
    free_dof_count: int
    constrained_dof_count: int
    stiffness_shape: tuple[int, int]
    stiffness_nnz: int
    element_recovery: list[ElementRecovery] = field(default_factory=list)
    history: list[dict[str, float | int | str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "converged": bool(self.converged),
            "residual_norm": float(self.residual_norm),
            "relative_residual_norm": float(self.relative_residual_norm),
            "status": self.status,
            "free_dof_count": int(self.free_dof_count),
            "constrained_dof_count": int(self.constrained_dof_count),
            "stiffness_shape": [int(self.stiffness_shape[0]), int(self.stiffness_shape[1])],
            "stiffness_nnz": int(self.stiffness_nnz),
            "element_recovery": [row.to_dict() for row in self.element_recovery],
            "history": [dict(row) for row in self.history],
            "metadata": dict(self.metadata),
        }


def _tet_b_matrix(coords: np.ndarray) -> tuple[np.ndarray, float]:
    x = np.ones((4, 4), dtype=float)
    x[:, 1:] = np.asarray(coords, dtype=float).reshape(4, 3)
    det = float(np.linalg.det(x))
    volume = abs(det) / 6.0
    if volume <= 1.0e-14:
        raise ValueError("Degenerate tetrahedron encountered during sparse linear assembly.")
    inv_x = np.linalg.inv(x)
    grads = inv_x[1:, :].T
    B = np.zeros((6, 12), dtype=float)
    for i, (bx, by, bz) in enumerate(grads):
        j = 3 * i
        B[0, j + 0] = bx
        B[1, j + 1] = by
        B[2, j + 2] = bz
        B[3, j + 0] = by
        B[3, j + 1] = bx
        B[4, j + 1] = bz
        B[4, j + 2] = by
        B[5, j + 0] = bz
        B[5, j + 2] = bx
    return B, volume


def _cell_tets(connectivity: Sequence[int]) -> list[tuple[int, int, int, int]]:
    conn = tuple(int(v) for v in connectivity)
    if len(conn) == 4:
        return [conn]
    if len(conn) >= 8:
        return [tuple(conn[i] for i in tet) for tet in HEX8_TO_TETS]
    return []


def _cell_dofs(connectivity: Sequence[int]) -> np.ndarray:
    return np.asarray([3 * int(node) + axis for node in connectivity for axis in range(3)], dtype=np.int64)


def _material_id_for_cell(mesh: Any, cell_index: int, fallback: str = "default") -> str:
    tags = getattr(mesh, "cell_tags", {}) or {}
    for key in ("material_id", "material", "material_name"):
        values = tags.get(key)
        if values is not None and cell_index < len(values):
            value = str(values[cell_index])
            if value:
                return value
    return fallback


def _material_for_cell(
    mesh: Any,
    cell_index: int,
    materials: Mapping[str, Mapping[str, Any] | LinearElasticMaterial] | None,
    default_material: LinearElasticMaterial,
) -> tuple[str, LinearElasticMaterial]:
    material_id = _material_id_for_cell(mesh, cell_index)
    raw = None if materials is None else materials.get(material_id)
    if isinstance(raw, LinearElasticMaterial):
        material = raw
    elif raw is not None:
        material = LinearElasticMaterial.from_mapping(raw)
    else:
        material = default_material
        material_id = "default" if material_id == "" else material_id
    material.validate()
    return material_id, material


def _assemble_sparse_system(
    mesh: Any,
    *,
    materials: Mapping[str, Mapping[str, Any] | LinearElasticMaterial] | None,
    default_material: LinearElasticMaterial,
    body_force: Sequence[float] | None,
) -> tuple[Any, np.ndarray, list[dict[str, Any]]]:
    nodes = np.asarray(getattr(mesh, "nodes", getattr(mesh, "points", [])), dtype=float).reshape((-1, 3))
    cells = [tuple(int(v) for v in cell) for cell in list(getattr(mesh, "cells", []) or [])]
    ndof = nodes.shape[0] * 3
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    rhs = np.zeros(ndof, dtype=float)
    recovery_data: list[dict[str, Any]] = []
    bf = None if body_force is None else np.asarray(body_force, dtype=float).reshape(3)

    for cell_id, conn in enumerate(cells):
        tets = _cell_tets(conn)
        if not tets:
            continue
        material_id, material = _material_for_cell(mesh, cell_id, materials, default_material)
        D = material.stiffness_matrix()
        local_index = {node: i for i, node in enumerate(conn)}
        B_weighted = np.zeros((6, len(conn) * 3), dtype=float)
        cell_volume = 0.0
        for tet in tets:
            Btet, volume = _tet_b_matrix(nodes[np.asarray(tet, dtype=np.int64)])
            kt = Btet.T @ D @ Btet * volume
            tdofs = _cell_dofs(tet)
            rr, cc = np.meshgrid(tdofs, tdofs, indexing="ij")
            rows.extend(int(v) for v in rr.ravel())
            cols.extend(int(v) for v in cc.ravel())
            data.extend(float(v) for v in kt.ravel())
            if bf is not None:
                nodal_force = bf * volume / 4.0
                for node in tet:
                    rhs[3 * int(node) : 3 * int(node) + 3] += nodal_force
            if material.unit_weight:
                for node in tet:
                    rhs[3 * int(node) + 2] += -float(material.unit_weight) * volume / 4.0
            for local_tet_i, node in enumerate(tet):
                local_cell_i = local_index.get(int(node))
                if local_cell_i is not None:
                    B_weighted[:, 3 * local_cell_i : 3 * local_cell_i + 3] += Btet[:, 3 * local_tet_i : 3 * local_tet_i + 3] * volume
            cell_volume += volume
        if cell_volume <= 0.0:
            continue
        recovery_data.append(
            {
                "cell_id": int(cell_id),
                "connectivity": conn,
                "material_id": material_id,
                "volume": float(cell_volume),
                "B": B_weighted / cell_volume,
                "D": D,
            }
        )

    if coo_matrix is not None:
        stiffness = coo_matrix((np.asarray(data, dtype=float), (np.asarray(rows), np.asarray(cols))), shape=(ndof, ndof)).tocsr()
        stiffness.backend = "scipy_sparse_csr"  # type: ignore[attr-defined]
    else:
        dense = np.zeros((ndof, ndof), dtype=float)
        if rows:
            np.add.at(dense, (np.asarray(rows, dtype=np.int64), np.asarray(cols, dtype=np.int64)), np.asarray(data, dtype=float))
        stiffness = _DenseMatrixAdapter(dense)
    return stiffness, rhs, recovery_data


def solve_sparse_linear_static(
    mesh: Any,
    *,
    materials: Mapping[str, Mapping[str, Any] | LinearElasticMaterial] | None = None,
    fixed_dofs: Mapping[int, float] | None = None,
    nodal_loads: Mapping[int, float] | None = None,
    body_force: Sequence[float] | None = None,
    default_material: LinearElasticMaterial | None = None,
    tolerance: float = 1.0e-9,
) -> SparseLinearStaticResult:
    """Assemble and solve a sparse small-strain linear-elastic static problem."""

    default_material = default_material or LinearElasticMaterial(E=1.0, nu=0.0)
    K, assembled_rhs, recovery_data = _assemble_sparse_system(
        mesh,
        materials=materials,
        default_material=default_material,
        body_force=body_force,
    )
    ndof = int(K.shape[0])
    rhs = np.asarray(assembled_rhs, dtype=float).reshape(ndof)
    for dof, value in dict(nodal_loads or {}).items():
        i = int(dof)
        if i < 0 or i >= ndof:
            raise IndexError(f"Nodal load DOF {i} is outside the valid range [0, {ndof}).")
        rhs[i] += float(value)

    fixed = {int(k): float(v) for k, v in dict(fixed_dofs or {}).items()}
    for dof in fixed:
        if dof < 0 or dof >= ndof:
            raise IndexError(f"Fixed DOF {dof} is outside the valid range [0, {ndof}).")
    constrained = np.asarray(sorted(fixed), dtype=np.int64)
    free = np.asarray([i for i in range(ndof) if i not in fixed], dtype=np.int64)
    u = np.zeros(ndof, dtype=float)
    if constrained.size:
        u[constrained] = np.asarray([fixed[int(i)] for i in constrained], dtype=float)

    status = str(getattr(K, "backend", "scipy_sparse_csr"))
    if free.size:
        Kff = K[free][:, free]
        rhs_free = rhs[free]
        if constrained.size:
            rhs_free = rhs_free - K[free][:, constrained] @ u[constrained]
        if spsolve is not None and csr_matrix is not None:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", MatrixRankWarning)
                solved = spsolve(Kff, rhs_free)
            if any(issubclass(item.category, MatrixRankWarning) for item in caught) or not np.all(np.isfinite(solved)):
                raise np.linalg.LinAlgError(
                    "Sparse linear static solve failed because the free stiffness block is singular or ill-conditioned. "
                    "Check boundary conditions, disconnected mesh regions, and interface constraints."
                )
        else:
            solved = np.linalg.solve(np.asarray(Kff, dtype=float), rhs_free)
        u[free] = np.asarray(solved, dtype=float).reshape(-1)
    else:
        status = "all_dofs_prescribed"

    residual = K @ u - rhs
    free_residual = residual[free] if free.size else np.zeros(0, dtype=float)
    residual_norm = float(np.linalg.norm(free_residual))
    reference_norm = float(np.linalg.norm(rhs[free])) if free.size else 1.0
    relative = residual_norm / max(reference_norm, 1.0)
    converged = bool(relative <= float(tolerance) or residual_norm <= float(tolerance))
    history = [
        {
            "step": 1,
            "iteration": 1,
            "residual_norm": residual_norm,
            "relative_residual_norm": relative,
            "status": status,
        }
    ]

    recovery: list[ElementRecovery] = []
    for row in recovery_data:
        conn = tuple(int(v) for v in row["connectivity"])
        dofs = _cell_dofs(conn)
        strain = np.asarray(row["B"], dtype=float) @ u[dofs]
        stress = np.asarray(row["D"], dtype=float) @ strain
        recovery.append(
            ElementRecovery(
                cell_id=int(row["cell_id"]),
                connectivity=conn,
                material_id=str(row["material_id"]),
                volume=float(row["volume"]),
                strain=strain,
                stress=stress,
            )
        )

    return SparseLinearStaticResult(
        converged=converged,
        displacement=u,
        residual_norm=residual_norm,
        relative_residual_norm=relative,
        status=status,
        free_dof_count=int(free.size),
        constrained_dof_count=int(constrained.size),
        stiffness_shape=(int(K.shape[0]), int(K.shape[1])),
        stiffness_nnz=int(K.nnz),
        element_recovery=recovery,
        history=history,
        metadata={
            "contract": "sparse_linear_static_v1",
            "tolerance": float(tolerance),
            "linear_solver_backend": status,
            "scipy_sparse_available": bool(spsolve is not None and csr_matrix is not None),
        },
    )


def affine_patch_displacement(point: Sequence[float]) -> np.ndarray:
    x, y, z = np.asarray(point, dtype=float).reshape(3)
    return np.array(
        [
            0.010 * x + 0.002 * y,
            -0.003 * x + 0.004 * y + 0.001 * z,
            0.002 * x - 0.001 * y + 0.005 * z,
        ],
        dtype=float,
    )


def affine_patch_strain() -> np.ndarray:
    return np.array([0.010, 0.004, 0.005, -0.001, 0.0, 0.002], dtype=float)


def run_hex8_linear_patch_benchmark() -> dict[str, Any]:
    from geoai_simkit.mesh.mesh_document import MeshDocument

    nodes = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    ]
    mesh = MeshDocument(
        nodes=nodes,
        cells=[tuple(range(8))],
        cell_types=["hex8"],
        cell_tags={"material_id": ["soil"]},
        metadata={"source": "hex8_linear_patch_benchmark"},
    )
    material = LinearElasticMaterial(E=25.0e6, nu=0.28)
    fixed = {
        3 * node_id + axis: float(affine_patch_displacement(point)[axis])
        for node_id, point in enumerate(nodes)
        for axis in range(3)
    }
    result = solve_sparse_linear_static(mesh, materials={"soil": material}, fixed_dofs=fixed, tolerance=1.0e-10)
    expected_strain = affine_patch_strain()
    expected_stress = material.stiffness_matrix() @ expected_strain
    strain_errors = [float(np.linalg.norm(row.strain - expected_strain)) for row in result.element_recovery]
    stress_errors = [float(np.linalg.norm(row.stress - expected_stress)) for row in result.element_recovery]
    max_strain_error = max(strain_errors, default=float("inf"))
    max_stress_error = max(stress_errors, default=float("inf"))
    passed = bool(result.converged and max_strain_error < 1.0e-12 and max_stress_error < 1.0e-5)
    return {
        "name": "hex8_sparse_linear_elastic_patch",
        "passed": passed,
        "status": "benchmark",
        "contract": "sparse_linear_static_v1",
        "max_strain_error": max_strain_error,
        "max_stress_error": max_stress_error,
        "residual_norm": result.residual_norm,
        "relative_residual_norm": result.relative_residual_norm,
        "linear_solver_backend": result.status,
        "stiffness_nnz": result.stiffness_nnz,
        "field_count": len(result.element_recovery),
    }


__all__ = [
    "ElementRecovery",
    "LinearElasticMaterial",
    "SparseLinearStaticResult",
    "affine_patch_displacement",
    "affine_patch_strain",
    "run_hex8_linear_patch_benchmark",
    "solve_sparse_linear_static",
]
