from __future__ import annotations

"""Executable GeoProjectDocument stage solver.

This module is intentionally compact and dependency-light.  It is not a
commercial nonlinear solver yet, but it performs the first real closed loop for
GeoProjectDocument:

1. Assemble solid element stiffness from compiled phase mesh/connectivity.
2. Materialize interface/contact candidates as penalty spring elements.
3. Maintain cell and interface state variables across construction phases.
4. Solve each phase incrementally and update stress/strain states.
5. Back-write nodal, cell, interface and engineering fields to ResultStore.

The current element path supports preview hex8 cells by internally decomposing
each hexahedron into linear tetrahedra.  Tet4 cells are assembled directly.
All code comments are in English by convention.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Mapping
import warnings

import numpy as np

try:
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import MatrixRankWarning, spsolve
except Exception:  # pragma: no cover - scipy is a declared runtime dependency
    csr_matrix = None  # type: ignore[assignment]
    MatrixRankWarning = Warning  # type: ignore[assignment]
    spsolve = None  # type: ignore[assignment]

from geoai_simkit.results.result_package import ResultFieldRecord, StageResult

try:  # Imported lazily by type users; avoids circular imports at module load time.
    from geoai_simkit.geoproject.document import (
        CompiledPhaseModel,
        EngineeringMetricRecord,
        GeoProjectDocument,
        ResultCurve,
    )
except Exception:  # pragma: no cover - static/type fallback only
    CompiledPhaseModel = Any  # type: ignore
    GeoProjectDocument = Any  # type: ignore
    EngineeringMetricRecord = Any  # type: ignore
    ResultCurve = Any  # type: ignore


HEX8_TO_TETS: tuple[tuple[int, int, int, int], ...] = (
    (0, 1, 3, 4),
    (1, 2, 3, 6),
    (1, 3, 4, 6),
    (1, 4, 5, 6),
    (3, 4, 6, 7),
)


@dataclass(slots=True)
class CellState:
    """Persistent integration state for one active volume cell."""

    cell_id: int
    material_id: str = ""
    strain: list[float] = field(default_factory=lambda: [0.0] * 6)
    stress: list[float] = field(default_factory=lambda: [0.0] * 6)
    plastic_strain: list[float] = field(default_factory=lambda: [0.0] * 6)
    internal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": int(self.cell_id),
            "material_id": self.material_id,
            "strain": list(self.strain),
            "stress": list(self.stress),
            "plastic_strain": list(self.plastic_strain),
            "internal": dict(self.internal),
        }


@dataclass(slots=True)
class InterfaceState:
    """Persistent state for one penalty interface spring."""

    interface_id: str
    master_ref: str = ""
    slave_ref: str = ""
    normal_gap: float = 0.0
    tangential_slip: float = 0.0
    normal_force: float = 0.0
    shear_force: float = 0.0
    contact_status: str = "open"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface_id": self.interface_id,
            "master_ref": self.master_ref,
            "slave_ref": self.slave_ref,
            "normal_gap": float(self.normal_gap),
            "tangential_slip": float(self.tangential_slip),
            "normal_force": float(self.normal_force),
            "shear_force": float(self.shear_force),
            "contact_status": self.contact_status,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PhaseSolveRecord:
    """Structured diagnostics from one phase solve."""

    phase_id: str
    active_cell_count: int
    active_interface_count: int
    total_dofs: int
    free_dofs: int
    constrained_dofs: int
    residual_norm: float
    max_displacement: float
    max_settlement: float
    max_von_mises_stress: float
    max_reaction_force: float = 0.0
    relative_residual_norm: float = 0.0
    convergence_tolerance: float = 1.0e-5
    converged: bool = False
    assembly_status: str = "ok"
    solve_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "active_cell_count": int(self.active_cell_count),
            "active_interface_count": int(self.active_interface_count),
            "total_dofs": int(self.total_dofs),
            "free_dofs": int(self.free_dofs),
            "constrained_dofs": int(self.constrained_dofs),
            "residual_norm": float(self.residual_norm),
            "relative_residual_norm": float(self.relative_residual_norm),
            "convergence_tolerance": float(self.convergence_tolerance),
            "converged": bool(self.converged),
            "max_displacement": float(self.max_displacement),
            "max_settlement": float(self.max_settlement),
            "max_von_mises_stress": float(self.max_von_mises_stress),
            "assembly_status": self.assembly_status,
            "solve_status": self.solve_status,
        }


@dataclass(slots=True)
class IncrementalSolveSummary:
    """Summary returned by run_geoproject_incremental_solve."""

    accepted: bool
    phase_records: list[PhaseSolveRecord]
    result_phase_count: int
    cell_state_count: int
    interface_state_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": bool(self.accepted),
            "phase_records": [row.to_dict() for row in self.phase_records],
            "result_phase_count": int(self.result_phase_count),
            "cell_state_count": int(self.cell_state_count),
            "interface_state_count": int(self.interface_state_count),
            "metadata": dict(self.metadata),
        }


def _elastic_matrix(E: float, nu: float) -> np.ndarray:
    E = max(float(E), 1.0)
    nu = min(max(float(nu), 0.0), 0.49)
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
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


def _material_parameters(material: Mapping[str, Any] | None) -> dict[str, float]:
    material = dict(material or {})
    params = dict(material.get("parameters", {}) or {})
    model_type = str(material.get("model_type", material.get("model", "linear_elastic"))).lower()
    E = params.get("E", params.get("E_ref", params.get("YoungModulus", params.get("EA", 30000.0))))
    nu = params.get("nu", params.get("poisson", 0.30))
    gamma = params.get("gamma_unsat", params.get("gamma", params.get("unit_weight", 18.0)))
    cohesion = params.get("cohesion", params.get("c_ref", params.get("c", 10.0)))
    phi = params.get("friction_deg", params.get("phi", params.get("phi_deg", 30.0)))
    # Placeholders are deliberately upgraded to stable engineering defaults.
    if "placeholder" in model_type:
        model_type = "mohr_coulomb_equivalent"
    return {
        "E": float(E),
        "nu": float(nu),
        "gamma": float(gamma),
        "cohesion": float(cohesion),
        "phi_deg": float(phi),
        "model_type": model_type,  # type: ignore[dict-item]
    }


def _tet_b_matrix(coords: np.ndarray) -> tuple[np.ndarray, float]:
    """Return B matrix and volume for a linear tetrahedron."""

    x = np.ones((4, 4), dtype=float)
    x[:, 1:] = coords[:, :3]
    det_j = float(np.linalg.det(x))
    volume = abs(det_j) / 6.0
    if volume < 1.0e-12:
        raise ValueError("Degenerate tetrahedron")
    inv_x = np.linalg.inv(x)
    grads = inv_x[1:, :].T  # rows: node, columns: dN/dx,dN/dy,dN/dz
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


def _cell_tets(connectivity: list[int]) -> list[tuple[int, int, int, int]]:
    if len(connectivity) == 4:
        return [tuple(int(v) for v in connectivity)]
    if len(connectivity) >= 8:
        return [tuple(int(connectivity[i]) for i in tet) for tet in HEX8_TO_TETS]
    return []


def _von_mises(stress: np.ndarray) -> float:
    sx, sy, sz, txy, tyz, txz = [float(v) for v in stress]
    value = 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy * txy + tyz * tyz + txz * txz)
    return sqrt(max(value, 0.0))


def _collect_materials(compiled: CompiledPhaseModel) -> dict[str, dict[str, Any]]:
    block = compiled.material_block or {}
    out: dict[str, dict[str, Any]] = {}
    for row in list(block.get("materials", []) or []):
        row = dict(row or {})
        mid = str(row.get("id", row.get("name", "material")))
        out[mid] = row
    return out


def _dof_indices(node_ids: list[int]) -> list[int]:
    out: list[int] = []
    for node in node_ids:
        base = 3 * int(node)
        out.extend([base, base + 1, base + 2])
    return out


def _cell_centroid(nodes: np.ndarray, connectivity: list[int]) -> np.ndarray:
    if not connectivity:
        return np.zeros(3, dtype=float)
    return np.mean(nodes[np.array(connectivity, dtype=int)], axis=0)


def _node_sets_from_bounds(nodes: np.ndarray, tol: float = 1.0e-8) -> dict[str, list[int]]:
    if nodes.size == 0:
        return {"bottom": [], "top": [], "xmin": [], "xmax": [], "ymin": [], "ymax": []}
    xmin, ymin, zmin = nodes.min(axis=0)
    xmax, ymax, zmax = nodes.max(axis=0)
    span = max(float(np.ptp(nodes[:, 0])), float(np.ptp(nodes[:, 1])), float(np.ptp(nodes[:, 2])), 1.0)
    eps = max(tol, span * 1.0e-7)
    return {
        "bottom": [int(i) for i, row in enumerate(nodes) if abs(row[2] - zmin) <= eps],
        "top": [int(i) for i, row in enumerate(nodes) if abs(row[2] - zmax) <= eps],
        "xmin": [int(i) for i, row in enumerate(nodes) if abs(row[0] - xmin) <= eps],
        "xmax": [int(i) for i, row in enumerate(nodes) if abs(row[0] - xmax) <= eps],
        "ymin": [int(i) for i, row in enumerate(nodes) if abs(row[1] - ymin) <= eps],
        "ymax": [int(i) for i, row in enumerate(nodes) if abs(row[1] - ymax) <= eps],
    }


def _constrained_dofs(nodes: np.ndarray, boundary_block: Mapping[str, Any]) -> set[int]:
    node_sets = _node_sets_from_bounds(nodes)
    constrained: set[int] = set()
    for bc in list(boundary_block.get("boundary_conditions", []) or []):
        bc = dict(bc or {})
        dof = str(bc.get("dof", "ux,uy,uz")).lower()
        location = str(dict(bc.get("metadata", {}) or {}).get("location", "")).lower()
        if "bottom" in location:
            target_nodes = node_sets["bottom"]
            axes = [0, 1, 2]
        elif "lateral" in location:
            target_nodes = sorted(set(node_sets["xmin"] + node_sets["xmax"] + node_sets["ymin"] + node_sets["ymax"]))
            axes = []
            if "ux" in dof or "un" in dof:
                axes.append(0)
            if "uy" in dof or "un" in dof:
                axes.append(1)
            if "uz" in dof:
                axes.append(2)
            if not axes:
                axes = [0, 1]
        else:
            target_nodes = node_sets["bottom"]
            axes = [0, 1, 2] if "ux" in dof and "uy" in dof and "uz" in dof else [2]
        for node in target_nodes:
            for axis in axes:
                constrained.add(3 * int(node) + int(axis))
    if not constrained:
        for node in node_sets["bottom"]:
            constrained.update([3 * node, 3 * node + 1, 3 * node + 2])
    return constrained


def _assemble_volume_elements(
    compiled: CompiledPhaseModel,
    nodes: np.ndarray,
    materials: dict[str, dict[str, Any]],
    previous_states: dict[int, CellState],
) -> tuple[np.ndarray, np.ndarray, dict[int, dict[str, Any]], dict[int, CellState]]:
    ndof = nodes.shape[0] * 3
    K = np.zeros((ndof, ndof), dtype=float)
    F = np.zeros(ndof, dtype=float)
    element_data: dict[int, dict[str, Any]] = {}
    state_table: dict[int, CellState] = {}
    elements = list((compiled.element_block or {}).get("elements", []) or [])

    for element in elements:
        row = dict(element or {})
        cell_id = int(row.get("cell_id", len(element_data)))
        connectivity = [int(v) for v in list(row.get("connectivity", []) or [])]
        tets = _cell_tets(connectivity)
        if not tets:
            continue
        material_id = str(row.get("material_id") or "default_soil")
        mat = _material_parameters(materials.get(material_id))
        C = _elastic_matrix(float(mat["E"]), float(mat["nu"]))
        cell_volume = 0.0
        B_weighted = np.zeros((6, max(len(connectivity), 1) * 3), dtype=float)
        local_index = {node: i for i, node in enumerate(connectivity)}
        for tet in tets:
            try:
                Btet, vt = _tet_b_matrix(nodes[np.array(tet, dtype=int)])
            except Exception:
                continue
            kt = Btet.T @ C @ Btet * vt
            gdofs = _dof_indices(list(tet))
            K[np.ix_(gdofs, gdofs)] += kt
            # Body force uses kN/m3-style units consistent with default project units.
            for node in tet:
                F[3 * node + 2] += -float(mat["gamma"]) * vt / 4.0
            cell_volume += vt
            if connectivity:
                for local_tet_i, node in enumerate(tet):
                    local_cell_i = local_index.get(node)
                    if local_cell_i is None:
                        continue
                    B_weighted[:, 3 * local_cell_i : 3 * local_cell_i + 3] += Btet[:, 3 * local_tet_i : 3 * local_tet_i + 3] * vt
        if cell_volume <= 0.0:
            continue
        B_avg = B_weighted / cell_volume
        previous = previous_states.get(cell_id)
        state = previous or CellState(cell_id=cell_id, material_id=material_id, internal={"model_type": mat["model_type"]})
        state.material_id = material_id
        state.internal.setdefault("model_type", mat["model_type"])
        state_table[cell_id] = state
        element_data[cell_id] = {
            "connectivity": connectivity,
            "B": B_avg,
            "volume": float(cell_volume),
            "material_id": material_id,
            "elastic_matrix": C,
        }
    return K, F, element_data, state_table


def _apply_surface_loads(compiled: CompiledPhaseModel, nodes: np.ndarray, F: np.ndarray) -> None:
    top_nodes = _node_sets_from_bounds(nodes)["top"]
    if not top_nodes:
        return
    loads = list((compiled.load_block or {}).get("loads", []) or [])
    if not loads:
        return
    xy_area = max(float(np.ptp(nodes[:, 0]) * np.ptp(nodes[:, 1])), 1.0)
    for load in loads:
        load = dict(load or {})
        components = dict(load.get("components", {}) or {})
        qz = float(components.get("qz", components.get("Fz", 0.0)))
        if abs(qz) <= 0.0:
            continue
        nodal = qz * xy_area / max(len(top_nodes), 1)
        for node in top_nodes:
            F[3 * int(node) + 2] += nodal


def _build_block_to_cells(compiled: CompiledPhaseModel) -> dict[str, list[int]]:
    block_to_cells: dict[str, list[int]] = {}
    entity_map = dict((compiled.mesh_block or {}).get("entity_map", {}) or {})
    raw = dict(entity_map.get("block_to_cells", {}) or {})
    for key, values in raw.items():
        block_to_cells[str(key)] = [int(v) for v in list(values or [])]
    if block_to_cells:
        return block_to_cells
    for row in list((compiled.element_block or {}).get("elements", []) or []):
        row = dict(row or {})
        block_id = str(row.get("volume_id", ""))
        if block_id:
            block_to_cells.setdefault(block_id, []).append(int(row.get("cell_id", 0)))
    return block_to_cells


def _assemble_interfaces(
    compiled: CompiledPhaseModel,
    nodes: np.ndarray,
    K: np.ndarray,
    element_data: dict[int, dict[str, Any]],
    previous_states: dict[str, InterfaceState],
) -> dict[str, InterfaceState]:
    interface_rows = list((compiled.interface_block or {}).get("interfaces", []) or [])
    block_to_cells = _build_block_to_cells(compiled)
    state_table: dict[str, InterfaceState] = {}
    for interface in interface_rows:
        interface = dict(interface or {})
        iid = str(interface.get("id", interface.get("name", "interface")))
        master_ref = str(interface.get("master_ref", ""))
        slave_ref = str(interface.get("slave_ref", ""))
        material_params = dict(interface.get("metadata", {}) or {})
        interface_material_id = str(interface.get("material_id", "") or "")
        material_rows = {str(row.get("id", row.get("name", ""))): dict(row) for row in list((compiled.material_block or {}).get("materials", []) or []) if isinstance(row, Mapping)}
        if interface_material_id and interface_material_id in material_rows:
            material_params.update(dict(material_rows[interface_material_id].get("parameters", {}) or {}))
        kn = float(material_params.get("kn", 1.0e4))
        ks = float(material_params.get("ks", max(kn * 0.5, 1.0)))
        friction_deg = float(material_params.get("friction_deg", material_params.get("phi", 25.0)) or 25.0)
        master_cells = [cid for cid in block_to_cells.get(master_ref, []) if cid in element_data]
        slave_cells = [cid for cid in block_to_cells.get(slave_ref, []) if cid in element_data]
        if not master_cells or not slave_cells:
            state_table[iid] = previous_states.get(iid) or InterfaceState(interface_id=iid, master_ref=master_ref, slave_ref=slave_ref, contact_status="inactive")
            continue
        # Use nearest cell-centroid nodes as a compact penalty interface.  This is
        # deliberately simple but creates a real stiffness contribution and state.
        master_conn = element_data[master_cells[0]]["connectivity"]
        slave_conn = element_data[slave_cells[0]]["connectivity"]
        cm = _cell_centroid(nodes, master_conn)
        cs = _cell_centroid(nodes, slave_conn)
        im = min(master_conn, key=lambda n: float(np.linalg.norm(nodes[int(n)] - cm)))
        js = min(slave_conn, key=lambda n: float(np.linalg.norm(nodes[int(n)] - cs)))
        delta = nodes[int(js)] - nodes[int(im)]
        norm = float(np.linalg.norm(delta))
        normal = delta / norm if norm > 1.0e-12 else np.array([0.0, 0.0, 1.0], dtype=float)
        spring = ks * np.eye(3, dtype=float) + max(kn - ks, 0.0) * np.outer(normal, normal)
        gdofs_i = [3 * int(im) + k for k in range(3)]
        gdofs_j = [3 * int(js) + k for k in range(3)]
        K[np.ix_(gdofs_i, gdofs_i)] += spring
        K[np.ix_(gdofs_j, gdofs_j)] += spring
        K[np.ix_(gdofs_i, gdofs_j)] -= spring
        K[np.ix_(gdofs_j, gdofs_i)] -= spring
        state = previous_states.get(iid) or InterfaceState(interface_id=iid, master_ref=master_ref, slave_ref=slave_ref)
        state.master_ref = master_ref
        state.slave_ref = slave_ref
        state.metadata.update({"master_node": int(im), "slave_node": int(js), "normal": normal.tolist(), "kn": kn, "ks": ks, "friction_deg": friction_deg, "material_id": interface_material_id, "contact_law": "penalty_coulomb_interface_v1"})
        state_table[iid] = state
    return state_table


def _solve_linear_system(K: np.ndarray, F: np.ndarray, constrained: set[int], *, tolerance: float = 1.0e-5) -> tuple[np.ndarray, np.ndarray, float, float, bool, str]:
    ndof = K.shape[0]
    u = np.zeros(ndof, dtype=float)
    free = np.array([i for i in range(ndof) if i not in constrained], dtype=int)
    if free.size == 0:
        reactions = K @ u - F
        residual_norm = float(np.linalg.norm(F))
        relative = residual_norm / max(float(np.linalg.norm(F)), 1.0)
        return u, reactions, residual_norm, relative, residual_norm <= float(tolerance), "no_free_dofs"
    Kff = K[np.ix_(free, free)]
    Ff = F[free]
    status = "dense_direct"
    try:
        if csr_matrix is not None and spsolve is not None:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", MatrixRankWarning)
                solved = spsolve(csr_matrix(Kff), Ff)
            if any(issubclass(item.category, MatrixRankWarning) for item in caught) or not np.all(np.isfinite(solved)):
                raise np.linalg.LinAlgError("sparse free stiffness block is singular")
            u[free] = np.asarray(solved, dtype=float)
            status = "sparse_direct"
        else:
            u[free] = np.linalg.solve(Kff, Ff)
    except np.linalg.LinAlgError:
        u[free] = np.linalg.lstsq(Kff, Ff, rcond=None)[0]
        status = "least_squares_singular"
    reactions = K @ u - F
    residual = reactions.copy()
    residual[list(constrained)] = 0.0
    residual_norm = float(np.linalg.norm(residual))
    relative = residual_norm / max(float(np.linalg.norm(Ff)), 1.0)
    converged = bool(relative <= float(tolerance) or residual_norm <= float(tolerance))
    return u, reactions, residual_norm, relative, converged, status


def _update_cell_states(
    element_data: dict[int, dict[str, Any]],
    state_table: dict[int, CellState],
    previous_u: np.ndarray,
    current_u: np.ndarray,
) -> None:
    for cell_id, data in element_data.items():
        conn = [int(v) for v in data["connectivity"]]
        if not conn:
            continue
        dofs = _dof_indices(conn)
        du = current_u[dofs] - previous_u[dofs]
        dstrain = np.asarray(data["B"], dtype=float) @ du
        state = state_table[cell_id]
        strain = np.asarray(state.strain, dtype=float) + dstrain
        stress = np.asarray(state.stress, dtype=float) + np.asarray(data["elastic_matrix"], dtype=float) @ dstrain
        # Lightweight Mohr-Coulomb-style state flag; stress is not returned to the
        # yield surface yet, but the state table records yielded cells for GUI use.
        params_model = str(state.internal.get("model_type", "linear_elastic"))
        vm = _von_mises(stress)
        cohesion = float(state.internal.get("cohesion", 10.0))
        yielded = bool("mohr" in params_model and vm > max(6.0 * cohesion, 1.0e6))
        state.strain = [float(v) for v in strain]
        state.stress = [float(v) for v in stress]
        state.internal["von_mises"] = float(vm)
        state.internal["yielded"] = yielded
        state.internal["updated_by"] = "geoproject_incremental_dense_solver"


def _update_interface_states(interface_states: dict[str, InterfaceState], u: np.ndarray) -> None:
    for state in interface_states.values():
        im = state.metadata.get("master_node")
        js = state.metadata.get("slave_node")
        if im is None or js is None:
            continue
        ui = u[3 * int(im) : 3 * int(im) + 3]
        uj = u[3 * int(js) : 3 * int(js) + 3]
        rel = uj - ui
        normal = np.asarray(state.metadata.get("normal", [0.0, 0.0, 1.0]), dtype=float)
        kn = float(state.metadata.get("kn", 1.0e4))
        ks = float(state.metadata.get("ks", 5.0e3))
        gap = float(np.dot(rel, normal))
        slip_vec = rel - gap * normal
        slip = float(np.linalg.norm(slip_vec))
        state.normal_gap = gap
        state.tangential_slip = slip
        state.normal_force = max(-kn * gap, 0.0)
        state.shear_force = ks * slip
        state.contact_status = "closed" if gap <= 0.0 else "open"


def _backwrite_phase_result(
    project: GeoProjectDocument,
    phase_id: str,
    compiled: CompiledPhaseModel,
    nodes: np.ndarray,
    u: np.ndarray,
    cell_states: dict[int, CellState],
    interface_states: dict[str, InterfaceState],
    record: PhaseSolveRecord,
    reactions: np.ndarray | None = None,
) -> None:
    stage = StageResult(stage_id=phase_id, metadata={"source": "geoproject_incremental_solver_v1", "solve_record": record.to_dict()})
    node_ids = [str(i) for i in range(nodes.shape[0])]
    stage.add_field(ResultFieldRecord(name="displacement", stage_id=phase_id, association="node", values=[float(v) for v in u], entity_ids=node_ids, components=3, metadata={"unit": project.project_settings.length_unit, "components": ["ux", "uy", "uz"]}))
    ux = [float(u[3 * i + 0]) for i in range(nodes.shape[0])]
    uy = [float(u[3 * i + 1]) for i in range(nodes.shape[0])]
    uz = [float(u[3 * i + 2]) for i in range(nodes.shape[0])]
    stage.add_field(ResultFieldRecord(name="ux", stage_id=phase_id, association="node", values=ux, entity_ids=node_ids, components=1, metadata={"unit": project.project_settings.length_unit}))
    stage.add_field(ResultFieldRecord(name="uy", stage_id=phase_id, association="node", values=uy, entity_ids=node_ids, components=1, metadata={"unit": project.project_settings.length_unit}))
    stage.add_field(ResultFieldRecord(name="uz", stage_id=phase_id, association="node", values=uz, entity_ids=node_ids, components=1, metadata={"unit": project.project_settings.length_unit}))
    if reactions is not None and reactions.size == u.size:
        stage.add_field(ResultFieldRecord(name="reaction_force", stage_id=phase_id, association="node", values=[float(v) for v in reactions], entity_ids=node_ids, components=3, metadata={"unit": project.project_settings.force_unit, "components": ["Rx", "Ry", "Rz"]}))
    active_cell_ids = [int(row.get("cell_id", 0)) for row in list((compiled.element_block or {}).get("elements", []) or []) if int(row.get("cell_id", 0)) in cell_states]
    stress_full = [float(v) for cid in active_cell_ids for v in cell_states[cid].stress]
    strain_full = [float(v) for cid in active_cell_ids for v in cell_states[cid].strain]
    stress_zz = [float(cell_states[cid].stress[2]) for cid in active_cell_ids]
    stress_vm = [float(cell_states[cid].internal.get("von_mises", _von_mises(np.asarray(cell_states[cid].stress, dtype=float)))) for cid in active_cell_ids]
    strain_eq = [float(np.linalg.norm(np.asarray(cell_states[cid].strain, dtype=float))) for cid in active_cell_ids]
    cell_entity_ids = [str(cid) for cid in active_cell_ids]
    stage.add_field(ResultFieldRecord(name="cell_stress", stage_id=phase_id, association="cell", values=stress_full, entity_ids=cell_entity_ids, components=6, metadata={"unit": project.project_settings.stress_unit, "components": ["sxx", "syy", "szz", "txy", "tyz", "txz"]}))
    stage.add_field(ResultFieldRecord(name="cell_strain", stage_id=phase_id, association="cell", values=strain_full, entity_ids=cell_entity_ids, components=6, metadata={"components": ["exx", "eyy", "ezz", "gxy", "gyz", "gxz"]}))
    stage.add_field(ResultFieldRecord(name="cell_stress_zz", stage_id=phase_id, association="cell", values=stress_zz, entity_ids=cell_entity_ids, components=1, metadata={"unit": project.project_settings.stress_unit}))
    stage.add_field(ResultFieldRecord(name="cell_von_mises", stage_id=phase_id, association="cell", values=stress_vm, entity_ids=cell_entity_ids, components=1, metadata={"unit": project.project_settings.stress_unit}))
    stage.add_field(ResultFieldRecord(name="cell_equivalent_strain", stage_id=phase_id, association="cell", values=strain_eq, entity_ids=cell_entity_ids, components=1))
    if interface_states:
        rows = list(interface_states.values())
        stage.add_field(ResultFieldRecord(name="interface_normal_gap", stage_id=phase_id, association="face", values=[float(s.normal_gap) for s in rows], entity_ids=[s.interface_id for s in rows], components=1, metadata={"unit": project.project_settings.length_unit}))
        stage.add_field(ResultFieldRecord(name="interface_shear_force", stage_id=phase_id, association="face", values=[float(s.shear_force) for s in rows], entity_ids=[s.interface_id for s in rows], components=1, metadata={"unit": project.project_settings.force_unit}))
    support_forces: dict[str, float] = {}
    for sid in compiled.metadata.get("active_structure_ids", []) or []:
        support_forces[str(sid)] = float(record.max_displacement * 1.0e4)
    stage.support_forces = support_forces
    stage.metrics.update(
        {
            "max_displacement": float(record.max_displacement),
            "max_settlement": float(record.max_settlement),
            "max_von_mises_stress": float(record.max_von_mises_stress),
            "max_reaction_force": float(record.max_reaction_force),
            "residual_norm": float(record.residual_norm),
            "active_cell_count": float(record.active_cell_count),
            "active_interface_count": float(record.active_interface_count),
        }
    )
    project.result_store.phase_results[phase_id] = stage
    for name, value in stage.metrics.items():
        metric_id = f"{phase_id}:{name}"
        project.result_store.engineering_metrics[metric_id] = EngineeringMetricRecord(id=metric_id, name=name, value=float(value), phase_id=phase_id, metadata={"source": "geoproject_incremental_solver_v1"})


def _refresh_result_curves(project: GeoProjectDocument) -> None:
    metric_names = sorted({name for result in project.result_store.phase_results.values() for name in result.metrics})
    phase_ids = project.phase_ids()
    for name in metric_names:
        x: list[float] = []
        y: list[float] = []
        stage_ids: list[str] = []
        for index, phase_id in enumerate(phase_ids):
            result = project.result_store.phase_results.get(phase_id)
            if result is None or name not in result.metrics:
                continue
            x.append(float(index))
            y.append(float(result.metrics[name]))
            stage_ids.append(phase_id)
        if y:
            project.result_store.curves[f"curve_{name}"] = ResultCurve(id=f"curve_{name}", name=name, x=x, y=y, x_label="phase_index", y_label=name, metadata={"stage_ids": stage_ids, "source": "geoproject_incremental_solver_v1"})


def run_geoproject_incremental_solve(project: GeoProjectDocument, *, compile_if_needed: bool = True, write_results: bool = True) -> IncrementalSolveSummary:
    """Run a small but executable staged FEM solve and write fields to ResultStore."""

    project.populate_default_framework_content()
    if compile_if_needed or not project.solver_model.compiled_phase_models:
        project.compile_phase_models()

    previous_u: np.ndarray | None = None
    previous_cell_states: dict[int, CellState] = {}
    previous_interface_states: dict[str, InterfaceState] = {}
    phase_records: list[PhaseSolveRecord] = []
    all_cell_states: dict[int, CellState] = {}
    all_interface_states: dict[str, InterfaceState] = {}

    for phase_id in project.phase_ids():
        compiled = project.solver_model.compiled_phase_models.get(f"compiled_{phase_id}")
        if compiled is None:
            continue
        nodes = np.asarray((compiled.mesh_block or {}).get("node_coordinates", []) or [], dtype=float)
        if nodes.size == 0:
            continue
        nodes = nodes.reshape((-1, 3))
        materials = _collect_materials(compiled)
        K, F, element_data, cell_states = _assemble_volume_elements(compiled, nodes, materials, previous_cell_states)
        _apply_surface_loads(compiled, nodes, F)
        interface_states = _assemble_interfaces(compiled, nodes, K, element_data, previous_interface_states)
        constrained = _constrained_dofs(nodes, compiled.boundary_block or {})
        calculation_settings = dict((compiled.solver_control_block or {}).get("calculation_settings", {}) or {})
        tolerance = float(calculation_settings.get("tolerance", 1.0e-5) or 1.0e-5)
        u, reactions, residual, relative_residual, converged, solve_status = _solve_linear_system(K, F, constrained, tolerance=tolerance)
        if previous_u is None or previous_u.shape != u.shape:
            previous_u = np.zeros_like(u)
        if converged:
            _update_cell_states(element_data, cell_states, previous_u, u)
            _update_interface_states(interface_states, u)
        else:
            for state in cell_states.values():
                state.internal["commit_status"] = "blocked_nonconverged"
                state.internal["relative_residual_norm"] = float(relative_residual)
            for state in interface_states.values():
                state.metadata["commit_status"] = "blocked_nonconverged"
                state.metadata["relative_residual_norm"] = float(relative_residual)
        max_disp = float(np.max(np.linalg.norm(u.reshape((-1, 3)), axis=1))) if u.size else 0.0
        max_settlement = float(abs(np.min(u[2::3]))) if u.size else 0.0
        max_vm = max((float(state.internal.get("von_mises", 0.0)) for state in cell_states.values()), default=0.0)
        max_reaction = float(np.max(np.linalg.norm(reactions.reshape((-1, 3)), axis=1))) if reactions.size else 0.0
        record = PhaseSolveRecord(
            phase_id=phase_id,
            active_cell_count=len(element_data),
            active_interface_count=len(interface_states),
            total_dofs=int(K.shape[0]),
            free_dofs=int(K.shape[0] - len(constrained)),
            constrained_dofs=len(constrained),
            residual_norm=float(residual),
            max_displacement=max_disp,
            max_settlement=max_settlement,
            max_von_mises_stress=max_vm,
            max_reaction_force=max_reaction,
            relative_residual_norm=float(relative_residual),
            convergence_tolerance=float(tolerance),
            converged=bool(converged),
            solve_status=solve_status,
        )
        compiled.metadata["AssemblyBlock"] = {
            "assembled": True,
            "stiffness_shape": [int(K.shape[0]), int(K.shape[1])],
            "nonzero_entries": int(np.count_nonzero(np.abs(K) > 0.0)),
            "load_norm": float(np.linalg.norm(F)),
            "active_cell_count": len(element_data),
        }
        compiled.metadata["IncrementalSolveBlock"] = record.to_dict()
        compiled.state_variable_block["cell_states"] = [state.to_dict() for state in cell_states.values()]
        compiled.state_variable_block["interface_states"] = [state.to_dict() for state in interface_states.values()]
        compiled.state_variable_block["committed"] = bool(converged)
        compiled.interface_block["materialized_interface_elements"] = [state.to_dict() for state in interface_states.values()]
        compiled.result_request_block["backwrite_status"] = "written_to_ResultStore" if write_results else "not_requested"
        if write_results and not converged:
            compiled.result_request_block["engineering_valid"] = False
            compiled.result_request_block["warning"] = "Results are diagnostic only because the phase did not satisfy the residual convergence tolerance."
        if write_results:
            _backwrite_phase_result(project, phase_id, compiled, nodes, u, cell_states, interface_states, record, reactions=reactions)
        if converged:
            previous_u = u.copy()
            previous_cell_states = {cid: state for cid, state in cell_states.items()}
            previous_interface_states = {iid: state for iid, state in interface_states.items()}
        all_cell_states.update(previous_cell_states)
        all_interface_states.update(previous_interface_states)
        phase_records.append(record)

    if write_results:
        _refresh_result_curves(project)
        project.mark_changed(["solver", "result"], action="run_geoproject_incremental_solve", affected_entities=[row.phase_id for row in phase_records])
    accepted = bool(phase_records) and all(row.converged for row in phase_records)
    project.solver_model.metadata["last_incremental_solve"] = {
        "contract": "geoproject_incremental_solver_v1",
        "accepted": bool(accepted),
        "phase_count": len(phase_records),
        "result_phase_count": len(project.result_store.phase_results),
        "cell_state_count": len(all_cell_states),
        "interface_state_count": len(all_interface_states),
        "phase_records": [row.to_dict() for row in phase_records],
        "accepted_by": "relative_residual_norm<=convergence_tolerance",
    }
    return IncrementalSolveSummary(
        accepted=accepted,
        phase_records=phase_records,
        result_phase_count=len(project.result_store.phase_results),
        cell_state_count=len(all_cell_states),
        interface_state_count=len(all_interface_states),
        metadata={"contract": "geoproject_incremental_solver_v1", "write_results": bool(write_results)},
    )


__all__ = [
    "CellState",
    "InterfaceState",
    "PhaseSolveRecord",
    "IncrementalSolveSummary",
    "run_geoproject_incremental_solve",
]
