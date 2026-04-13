from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoai_simkit.core.model import (
    BoundaryCondition,
    InterfaceDefinition,
    LoadDefinition,
    StructuralElementDefinition,
)
from geoai_simkit.materials import MaterialModel, MaterialState
from geoai_simkit.solver.hex8_linear import (
    GAUSS,
    Hex8Submesh,
    bmatrix_hex8,
    element_body_force_hex8,
    select_bc_nodes,
)
from geoai_simkit.solver.interface_elements import InterfaceElementState, assemble_interface_response
from geoai_simkit.solver.linear_algebra import solve_linear_system
from geoai_simkit.solver.structural_elements import (
    StructuralDofMap,
    apply_structural_loads,
    assemble_structural_stiffness,
    build_structural_dof_map,
)


GAUSS_POINTS = [(xi, eta, zeta) for xi in GAUSS for eta in GAUSS for zeta in GAUSS]


@dataclass(slots=True)
class NonlinearSolveResult:
    u_nodes: np.ndarray
    structural_rotations: np.ndarray
    cell_stress: np.ndarray
    von_mises: np.ndarray
    cell_yield_fraction: np.ndarray
    cell_eq_plastic: np.ndarray
    gp_states: list[list[MaterialState]]
    interface_states: dict[str, list[InterfaceElementState]]
    warnings: list[str]
    dof_map: StructuralDofMap
    convergence_history: list[dict[str, float | int | str]] = field(default_factory=list)


def von_mises(stress6: np.ndarray) -> np.ndarray:
    s = np.asarray(stress6, dtype=float)
    sx, sy, sz, txy, tyz, txz = s.T
    return np.sqrt(np.maximum(0.0, 0.5*((sx-sy)**2 + (sy-sz)**2 + (sz-sx)**2) + 3.0*(txy**2 + tyz**2 + txz**2)))


def _clone_gp_states(states: list[list[MaterialState]]) -> list[list[MaterialState]]:
    return [[MaterialState(
        stress=s.stress.copy(),
        strain=s.strain.copy(),
        plastic_strain=s.plastic_strain.copy(),
        internal=dict(s.internal),
    ) for s in elem_states] for elem_states in states]


def _clone_interface_states(states: dict[str, list[InterfaceElementState]]) -> dict[str, list[InterfaceElementState]]:
    return {k: [InterfaceElementState(slip=s.slip.copy(), closed=s.closed, traction=s.traction.copy()) for s in v] for k, v in states.items()}


class NonlinearHex8Solver:
    def __init__(
        self,
        submesh: Hex8Submesh,
        materials: list[MaterialModel],
        gravity: tuple[float, float, float],
    ) -> None:
        self.submesh = submesh
        self.materials = materials
        self.gravity = gravity
        self._gp_cache = self._build_gp_cache()

    def _build_gp_cache(self) -> list[list[tuple[np.ndarray, float]]]:
        cache: list[list[tuple[np.ndarray, float]]] = []
        for elem in self.submesh.elements:
            coords = self.submesh.points[elem]
            gp = []
            for xi, eta, zeta in GAUSS_POINTS:
                B, detJ, _ = bmatrix_hex8(coords, xi, eta, zeta)
                gp.append((B, detJ))
            cache.append(gp)
        return cache

    def _build_external_force(self, loads: tuple[LoadDefinition, ...], ndof: int, dof_map: StructuralDofMap) -> np.ndarray:
        F = np.zeros(ndof, dtype=float)
        for eidx, elem in enumerate(self.submesh.elements):
            coords = self.submesh.points[elem]
            mat = self.materials[eidx]
            rho = float(mat.describe().get("rho") or 0.0)
            fe = element_body_force_hex8(coords, rho, self.gravity)
            edofs = self._trans_edofs(elem)
            F[edofs] += fe
        apply_structural_loads(F, self.submesh, dof_map, loads)
        for load in loads:
            if load.kind.lower() != "point_force":
                continue
            target = load.target.lower()
            if target == "all":
                node_ids = np.arange(self.submesh.points.shape[0], dtype=np.int64)
            else:
                node_ids = np.asarray(load.metadata.get("point_ids", []), dtype=np.int64)
            if node_ids.size == 0:
                continue
            value = np.asarray(load.values, dtype=float)
            for gid in node_ids:
                if int(gid) not in self.submesh.local_by_global:
                    continue
                nid = self.submesh.local_by_global[int(gid)]
                F[3 * nid: 3 * nid + 3] += value[:3]
        return F

    @staticmethod
    def _trans_edofs(elem: np.ndarray) -> np.ndarray:
        edofs = np.zeros(24, dtype=np.int64)
        for a, nid in enumerate(elem):
            edofs[3 * a: 3 * a + 3] = [3 * nid, 3 * nid + 1, 3 * nid + 2]
        return edofs

    def _dirichlet_data(
        self,
        bcs: tuple[BoundaryCondition, ...],
        scale: float,
        dof_map: StructuralDofMap,
    ) -> tuple[np.ndarray, np.ndarray]:
        fixed_dofs: list[int] = []
        fixed_values: list[float] = []
        for bc in bcs:
            kind = bc.kind.lower()
            if kind not in {"displacement", "rotation"}:
                continue
            node_ids = select_bc_nodes(self.submesh.points, bc)
            vals = np.asarray(bc.values, dtype=float) * scale
            for nid in node_ids:
                nid = int(nid)
                if kind == "displacement":
                    for comp in bc.components:
                        fixed_dofs.append(3 * nid + int(comp))
                        fixed_values.append(float(vals[min(comp, len(vals) - 1)]))
                elif kind == "rotation" and dof_map.has_rotation(nid):
                    rdofs = dof_map.rot_dofs(nid)
                    for comp in bc.components:
                        fixed_dofs.append(int(rdofs[int(comp)]))
                        fixed_values.append(float(vals[min(comp, len(vals) - 1)]))
        fixed_dofs_arr = np.asarray(fixed_dofs, dtype=np.int64)
        fixed_values_arr = np.asarray(fixed_values, dtype=float)
        if fixed_dofs_arr.size == 0:
            zmin_nodes = np.where(np.isclose(self.submesh.points[:, 2], self.submesh.points[:, 2].min()))[0]
            if zmin_nodes.size:
                fixed_dofs_arr = np.array([3 * int(zmin_nodes[0]), 3 * int(zmin_nodes[0]) + 1, 3 * int(zmin_nodes[0]) + 2], dtype=np.int64)
                fixed_values_arr = np.zeros(3, dtype=float)
        return fixed_dofs_arr, fixed_values_arr

    def _assemble_continuum_response(
        self,
        du_step_trans: np.ndarray,
        base_states: list[list[MaterialState]],
        total_ndof: int,
    ) -> tuple[np.ndarray, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray]:
        K = np.zeros((total_ndof, total_ndof), dtype=float)
        Fint = np.zeros(total_ndof, dtype=float)
        trial_states: list[list[MaterialState]] = []
        cell_stress = np.zeros((self.submesh.elements.shape[0], 6), dtype=float)
        cell_yield = np.zeros(self.submesh.elements.shape[0], dtype=float)
        cell_eqp = np.zeros(self.submesh.elements.shape[0], dtype=float)

        for eidx, elem in enumerate(self.submesh.elements):
            edofs = self._trans_edofs(elem)
            ue = du_step_trans[edofs]
            mat = self.materials[eidx]
            Ke = np.zeros((24, 24), dtype=float)
            fe_int = np.zeros(24, dtype=float)
            elem_states: list[MaterialState] = []
            stresses = []
            yielded_count = 0
            eqp_vals = []
            for gp_idx, (B, detJ) in enumerate(self._gp_cache[eidx]):
                dstrain = B @ ue
                new_state = mat.update(dstrain, base_states[eidx][gp_idx])
                D = mat.tangent_matrix(new_state)
                sigma = np.asarray(new_state.stress, dtype=float)
                Ke += B.T @ D @ B * detJ
                fe_int += B.T @ sigma * detJ
                elem_states.append(new_state)
                stresses.append(sigma)
                yielded_count += 1 if bool(new_state.internal.get("yielded", False)) else 0
                eqp_vals.append(float(new_state.internal.get("eps_p_eq", new_state.internal.get("eps_p_shear", 0.0))))
            K[np.ix_(edofs, edofs)] += Ke
            Fint[edofs] += fe_int
            trial_states.append(elem_states)
            cell_stress[eidx] = np.mean(np.asarray(stresses, dtype=float), axis=0)
            cell_yield[eidx] = yielded_count / max(1, len(elem_states))
            cell_eqp[eidx] = float(np.mean(eqp_vals)) if eqp_vals else 0.0
        return K, Fint, trial_states, cell_stress, cell_yield, cell_eqp

    def _evaluate_state(
        self,
        u_guess: np.ndarray,
        u_step_base: np.ndarray,
        base_states: list[list[MaterialState]],
        struct_K: np.ndarray,
        interfaces: list[InterfaceDefinition],
        local_interface_states: dict[str, list[InterfaceElementState]],
        ndof: int,
        n_nodes: int,
    ) -> tuple[np.ndarray, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray, dict[str, list[InterfaceElementState]], list[str]]:
        warnings: list[str] = []
        du_step = u_guess - u_step_base
        Kc, Fint_c, trial_states, cell_stress, cell_yield, cell_eqp = self._assemble_continuum_response(du_step[: n_nodes * 3], base_states, ndof)
        K = Kc + struct_K
        Fint = Fint_c + struct_K @ u_guess
        iface_trial = _clone_interface_states(local_interface_states)
        if interfaces:
            u_nodes_guess = u_guess[: n_nodes * 3].reshape(n_nodes, 3)
            int_asm, iface_trial = assemble_interface_response(interfaces, self.submesh, u_nodes_guess, iface_trial)
            K[: n_nodes * 3, : n_nodes * 3] += int_asm.K
            Fint[: n_nodes * 3] += int_asm.Fint
            warnings.extend(int_asm.warnings)
        return K, Fint, trial_states, cell_stress, cell_yield, cell_eqp, iface_trial, warnings

    @staticmethod
    def _residual_norm(residual: np.ndarray, free: np.ndarray, target: np.ndarray) -> tuple[float, float]:
        rnorm = float(np.linalg.norm(residual[free])) if free.size else 0.0
        fnorm = max(1.0, float(np.linalg.norm(target[free])) if free.size else 1.0)
        return rnorm, fnorm

    def _line_search(
        self,
        u_guess: np.ndarray,
        du: np.ndarray,
        free: np.ndarray,
        fixed_dofs: np.ndarray,
        fixed_values: np.ndarray,
        target: np.ndarray,
        rnorm0: float,
        u_step_base: np.ndarray,
        base_states: list[list[MaterialState]],
        struct_K: np.ndarray,
        interfaces: list[InterfaceDefinition],
        local_interface_states: dict[str, list[InterfaceElementState]],
        ndof: int,
        n_nodes: int,
        max_iter: int = 6,
    ) -> tuple[np.ndarray, float]:
        alpha = 1.0
        best_u = u_guess.copy()
        best_metric = rnorm0
        for _ in range(max_iter):
            trial = u_guess.copy()
            # `du` may be supplied either as a full-length increment vector (same size as
            # the global displacement vector) or as the reduced increment over the free
            # DOFs only. Accept both shapes so line-search stays compatible with callers
            # using structural/extended DOFs.
            if du.shape == trial.shape:
                trial[free] += alpha * du[free]
            elif du.shape == trial[free].shape:
                trial[free] += alpha * du
            else:
                raise ValueError(
                    f"Line-search increment size mismatch: du.shape={du.shape}, "
                    f"trial.shape={trial.shape}, free.shape={trial[free].shape}"
                )
            if fixed_dofs.size:
                trial[fixed_dofs] = fixed_values
            _, Fint, _, _, _, _, _, _ = self._evaluate_state(
                trial, u_step_base, base_states, struct_K, interfaces, local_interface_states, ndof, n_nodes
            )
            residual = target - Fint
            if fixed_dofs.size:
                residual[fixed_dofs] = 0.0
            metric = float(np.linalg.norm(residual[free])) if free.size else 0.0
            if metric <= best_metric * (1.0 - 1.0e-4 * alpha) or metric < best_metric:
                best_u = trial
                best_metric = metric
                break
            alpha *= 0.5
        return best_u, alpha

    def solve(
        self,
        bcs: tuple[BoundaryCondition, ...],
        loads: tuple[LoadDefinition, ...],
        gp_states: list[list[MaterialState]] | None = None,
        n_steps: int = 8,
        max_iterations: int = 12,
        tolerance: float = 1e-5,
        structures: list[StructuralElementDefinition] | None = None,
        interfaces: list[InterfaceDefinition] | None = None,
        interface_states: dict[str, list[InterfaceElementState]] | None = None,
        prefer_sparse: bool = True,
        line_search: bool = True,
        max_cutbacks: int = 5,
        progress_callback=None,
        cancel_check=None,
        stage_name: str | None = None,
    ) -> NonlinearSolveResult:
        n_nodes = self.submesh.points.shape[0]
        trans_ndof = n_nodes * 3
        warnings: list[str] = []
        convergence_history: list[dict[str, float | int | str]] = []
        if gp_states is None:
            gp_states = [[mat.create_state() for _ in range(len(GAUSS_POINTS))] for mat in self.materials]
        if interface_states is None:
            interface_states = {}
        structures = structures or []
        interfaces = interfaces or []

        dof_map = build_structural_dof_map(structures, self.submesh)
        ndof = dof_map.total_ndof
        u_committed = np.zeros(ndof, dtype=float)
        F_total = self._build_external_force(loads, ndof, dof_map)
        struct_asm = assemble_structural_stiffness(structures, self.submesh, dof_map=dof_map)
        warnings.extend(struct_asm.warnings)
        F_total += struct_asm.F
        all_dofs = np.arange(ndof, dtype=np.int64)
        last_cell_stress = np.zeros((self.submesh.elements.shape[0], 6), dtype=float)
        last_yield = np.zeros(self.submesh.elements.shape[0], dtype=float)
        last_eqp = np.zeros(self.submesh.elements.shape[0], dtype=float)

        total_steps = max(1, int(n_steps))
        current_lambda = 0.0
        load_increment = 1.0 / total_steps
        cutbacks = 0
        step_id = 0

        while current_lambda < 1.0 - 1.0e-12:
            if cancel_check and cancel_check():
                warnings.append('Solve canceled by user.')
                break
            lam_target = min(1.0, current_lambda + load_increment)
            step_id += 1
            fixed_dofs, fixed_values = self._dirichlet_data(bcs, scale=lam_target, dof_map=dof_map)
            free = np.setdiff1d(all_dofs, fixed_dofs)
            base_states = _clone_gp_states(gp_states)
            iface_base = _clone_interface_states(interface_states)
            u_step_base = u_committed.copy()
            u_guess = u_step_base.copy()
            if fixed_dofs.size:
                u_guess[fixed_dofs] = fixed_values
            target = F_total * lam_target
            best_metric = np.inf
            best_u = u_guess.copy()
            best_states = base_states
            best_iface = iface_base
            converged = False

            for it in range(1, max(1, max_iterations) + 1):
                if cancel_check and cancel_check():
                    warnings.append('Solve canceled by user.')
                    break
                K, Fint, trial_states, cell_stress, cell_yield, cell_eqp, iface_trial, iter_warnings = self._evaluate_state(
                    u_guess, u_step_base, base_states, struct_asm.K, interfaces, iface_base, ndof, n_nodes
                )
                warnings.extend(iter_warnings)
                residual = target - Fint
                if fixed_dofs.size:
                    residual[fixed_dofs] = 0.0
                    u_guess[fixed_dofs] = fixed_values
                rnorm, fnorm = self._residual_norm(residual, free, target)
                metric = rnorm / fnorm if fnorm else rnorm
                entry = {
                    'stage': stage_name or '',
                    'step': step_id,
                    'lambda': float(lam_target),
                    'iteration': it,
                    'residual_norm': rnorm,
                    'force_norm': fnorm,
                    'ratio': metric,
                    'load_increment': float(load_increment),
                }
                convergence_history.append(entry)
                if progress_callback is not None:
                    try:
                        progress_callback(dict(entry))
                    except Exception:
                        pass
                if metric < best_metric:
                    best_metric = metric
                    best_u = u_guess.copy()
                    best_states = trial_states
                    best_iface = iface_trial
                    last_cell_stress = cell_stress
                    last_yield = cell_yield
                    last_eqp = cell_eqp
                if metric < tolerance:
                    converged = True
                    u_committed = u_guess.copy()
                    gp_states = trial_states
                    interface_states = iface_trial
                    current_lambda = lam_target
                    if it <= 3 and load_increment < 0.5:
                        load_increment = min(1.0 - current_lambda, load_increment * 1.25)
                    break
                if free.size == 0:
                    break
                Kff = K[np.ix_(free, free)]
                du_free, solve_info = solve_linear_system(Kff, residual[free], prefer_sparse=prefer_sparse)
                warnings.extend(solve_info.warnings)
                convergence_history[-1]['linear_backend'] = solve_info.backend
                du_full = np.zeros_like(u_guess)
                du_full[free] = du_free
                if line_search:
                    u_next, alpha = self._line_search(
                        u_guess, du_full, free, fixed_dofs, fixed_values, target, rnorm,
                        u_step_base, base_states, struct_asm.K, interfaces, iface_base, ndof, n_nodes,
                    )
                    convergence_history[-1]['line_search_alpha'] = float(alpha)
                    u_guess = u_next
                else:
                    u_guess[free] += du_free
                if fixed_dofs.size:
                    u_guess[fixed_dofs] = fixed_values

            if not converged:
                if cutbacks < max_cutbacks and load_increment > 1.0e-3:
                    cutbacks += 1
                    load_increment *= 0.5
                    warnings.append(f'Nonlinear step cutback triggered at lambda={lam_target:.4f}; retrying with increment={load_increment:.4f}.')
                    step_id -= 1
                    continue
                warnings.append(f'Nonlinear solve stopped without convergence at lambda={lam_target:.4f}; best ratio={best_metric:.3e}.')
                u_committed = best_u
                gp_states = best_states
                interface_states = best_iface
                current_lambda = lam_target

        u_nodes = u_committed[:trans_ndof].reshape(n_nodes, 3)
        structural_rot = dof_map.structural_rotation_field(n_nodes, u_committed)
        return NonlinearSolveResult(
            u_nodes=u_nodes,
            structural_rotations=structural_rot,
            cell_stress=last_cell_stress,
            von_mises=von_mises(last_cell_stress),
            cell_yield_fraction=last_yield,
            cell_eq_plastic=last_eqp,
            gp_states=gp_states,
            interface_states=interface_states,
            warnings=warnings,
            dof_map=dof_map,
            convergence_history=convergence_history,
        )
