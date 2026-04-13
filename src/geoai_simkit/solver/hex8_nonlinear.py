from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import time

import numpy as np

from geoai_simkit.core.model import (
    BoundaryCondition,
    InterfaceDefinition,
    LoadDefinition,
    StructuralElementDefinition,
)
from geoai_simkit.materials import MaterialModel, MaterialState
from geoai_simkit.materials.linear_elastic import LinearElastic
from geoai_simkit.solver.hex8_linear import (
    GAUSS,
    Hex8Submesh,
    _build_element_dof_map,
    _canonical_element_signature,
    bmatrix_hex8,
    element_body_force_hex8,
    element_stiffness_hex8,
    select_bc_nodes,
)
from geoai_simkit.solver.interface_elements import InterfaceElementState, assemble_interface_block_response, assemble_interface_response
from geoai_simkit.solver.linear_algebra import LinearSolverContext, _optional_import, solve_linear_system
from geoai_simkit.solver.structural_elements import (
    StructuralAssemblyResult,
    StructuralDofMap,
    StructuralHybridAssemblyResult,
    apply_structural_loads,
    assemble_structural_hybrid_response,
    assemble_structural_stiffness,
    build_structural_dof_map,
)
from geoai_simkit.solver.warp_hex8 import build_block_sparse_pattern, build_node_block_sparse_pattern, block_values_matvec, block_values_to_csr, resolve_warp_hex8_config, try_warp_hex8_linear_assembly
from geoai_simkit.solver.warp_nonlinear import try_warp_nonlinear_continuum_assembly


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
    return np.sqrt(np.maximum(0.0, 0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3.0 * (txy**2 + tyz**2 + txz**2)))



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
        self._element_edofs = _build_element_dof_map(self.submesh.elements)
        self._shape_signatures = [_canonical_element_signature(self.submesh.points[elem]) for elem in self.submesh.elements]
        self._body_force_cache: dict[tuple[tuple[float, ...], float, tuple[float, float, float]], np.ndarray] = {}
        self._sp = _optional_import('scipy.sparse')
        self._gp_cache = self._build_gp_cache()
        self._all_linear_elastic = bool(self.materials) and all(isinstance(mat, LinearElastic) for mat in self.materials)
        self._linear_D = [mat.elastic_matrix() for mat in self.materials if isinstance(mat, LinearElastic)] if self._all_linear_elastic else []
        self._sparse_rows_template = np.repeat(self._element_edofs, 24, axis=1).reshape(-1).astype(np.int64, copy=False)
        self._sparse_cols_template = np.tile(self._element_edofs, (1, 24)).reshape(-1).astype(np.int64, copy=False)
        self._block_pattern = build_block_sparse_pattern(self.submesh.elements)
        self._constant_continuum_cache_key: tuple[int, bool, str, tuple[tuple[str, str], ...]] | None = None
        self._constant_continuum_K: Any | None = None
        self._constant_continuum_backend: dict[str, object] = {'backend': 'unset', 'used_warp': False, 'warnings': []}
        self._current_compute_device: str = 'cpu'
        self._current_solver_metadata: dict[str, Any] = {}

    def _build_gp_cache(self) -> list[list[tuple[np.ndarray, float]]]:
        cache: dict[tuple[float, ...], list[tuple[np.ndarray, float]]] = {}
        out: list[list[tuple[np.ndarray, float]]] = []
        for elem, sig in zip(self.submesh.elements, self._shape_signatures):
            gp = cache.get(sig)
            if gp is None:
                coords = self.submesh.points[elem]
                gp = []
                for xi, eta, zeta in GAUSS_POINTS:
                    B, detJ, _ = bmatrix_hex8(coords, xi, eta, zeta)
                    gp.append((B, detJ))
                cache[sig] = gp
            out.append(gp)
        return out

    def _ensure_constant_linear_continuum(
        self,
        total_ndof: int,
        *,
        prefer_sparse: bool,
        compute_device: str,
        solver_metadata: dict[str, Any] | None,
    ) -> dict[str, object]:
        if not self._all_linear_elastic:
            return {'backend': 'disabled', 'used_warp': False, 'warnings': []}
        meta = dict(solver_metadata or {})
        meta_key = tuple(sorted((str(k), str(v)) for k, v in meta.items() if isinstance(v, (str, int, float, bool))))
        pattern_key = (bytes(np.asarray(self._block_pattern.rows, dtype=np.int32)), bytes(np.asarray(self._block_pattern.cols, dtype=np.int32)))
        cache_key = (int(total_ndof), bool(prefer_sparse), str(compute_device), meta_key, pattern_key)
        if self._constant_continuum_cache_key == cache_key and self._constant_continuum_K is not None:
            return dict(self._constant_continuum_backend)

        trans_ndof = int(self.submesh.points.shape[0] * 3)
        sparse_ok = bool(prefer_sparse and self._sp is not None and trans_ndof >= 900)
        K_trans = None
        backend: dict[str, object] = {'backend': 'cpu-constant-linear', 'used_warp': False, 'warnings': []}

        if sparse_ok:
            warp_cfg = resolve_warp_hex8_config(meta)
            warp_K, _, warp_info = try_warp_hex8_linear_assembly(
                self.submesh.points,
                self.submesh.elements,
                np.asarray([float(mat.E) for mat in self.materials], dtype=float),
                np.asarray([float(mat.nu) for mat in self.materials], dtype=float),
                np.asarray([float(mat.rho) for mat in self.materials], dtype=float),
                (0.0, 0.0, 0.0),
                ndof=trans_ndof,
                requested_device=str(compute_device),
                config=warp_cfg,
                block_pattern=self._block_pattern,
            )
            backend = {
                'backend': str(warp_info.backend),
                'device': str(warp_info.device),
                'used_warp': bool(warp_info.used),
                'precision': str(warp_info.precision),
                'element_count': int(warp_info.element_count),
                'warnings': list(warp_info.warnings),
            }
            if warp_K is not None:
                K_trans = warp_K

        if K_trans is None:
            if sparse_ok:
                data = np.empty((self.submesh.elements.shape[0] * 24 * 24,), dtype=float)
            else:
                data = None
                K_trans = np.zeros((trans_ndof, trans_ndof), dtype=float)
            response_cache: dict[tuple[tuple[float, ...], float, float], np.ndarray] = {}
            cursor = 0
            for eidx, elem in enumerate(self.submesh.elements):
                coords = self.submesh.points[elem]
                mat = self.materials[eidx]
                assert isinstance(mat, LinearElastic)
                local_key = (self._shape_signatures[eidx], float(mat.E), float(mat.nu))
                Ke = response_cache.get(local_key)
                if Ke is None:
                    Ke = element_stiffness_hex8(coords, mat.elastic_matrix())
                    response_cache[local_key] = Ke
                edofs = self._element_edofs[eidx]
                if sparse_ok:
                    data[cursor: cursor + 24 * 24] = np.asarray(Ke, dtype=float).reshape(-1)
                    cursor += 24 * 24
                else:
                    K_trans[np.ix_(edofs, edofs)] += Ke
            if sparse_ok:
                K_trans = self._sp.coo_matrix((data, (self._sparse_rows_template, self._sparse_cols_template)), shape=(trans_ndof, trans_ndof)).tocsr()
                backend = {'backend': 'cpu-constant-linear-sparse', 'used_warp': False, 'warnings': list(backend.get('warnings', []))}

        if total_ndof > trans_ndof:
            if hasattr(K_trans, 'to_csr'):
                K_base = K_trans.to_csr()
                zero_tail = self._sp.csr_matrix((total_ndof - trans_ndof, total_ndof - trans_ndof), dtype=float) if self._sp is not None else None
                self._constant_continuum_K = self._sp.bmat([[K_base, None], [None, zero_tail]], format='csr') if self._sp is not None else K_base
            elif self._sp is not None and getattr(self._sp, 'issparse', lambda *_: False)(K_trans):
                zero_tail = self._sp.csr_matrix((total_ndof - trans_ndof, total_ndof - trans_ndof), dtype=float)
                self._constant_continuum_K = self._sp.bmat([[K_trans, None], [None, zero_tail]], format='csr')
            else:
                K_full = np.zeros((total_ndof, total_ndof), dtype=float)
                K_full[:trans_ndof, :trans_ndof] = np.asarray(K_trans, dtype=float)
                self._constant_continuum_K = K_full
        else:
            self._constant_continuum_K = K_trans

        self._constant_continuum_cache_key = cache_key
        self._constant_continuum_backend = dict(backend)
        return dict(backend)

    def _body_force_for_element(self, eidx: int) -> np.ndarray:
        sig = self._shape_signatures[eidx]
        mat = self.materials[eidx]
        rho = float(mat.describe().get('rho') or 0.0)
        key = (sig, rho, tuple(float(v) for v in self.gravity))
        cached = self._body_force_cache.get(key)
        if cached is None:
            coords = self.submesh.points[self.submesh.elements[eidx]]
            cached = element_body_force_hex8(coords, rho, self.gravity)
            self._body_force_cache[key] = cached
        return cached

    def _build_external_force(self, loads: tuple[LoadDefinition, ...], ndof: int, dof_map: StructuralDofMap) -> np.ndarray:
        F = np.zeros(ndof, dtype=float)
        for eidx in range(self.submesh.elements.shape[0]):
            F[self._element_edofs[eidx]] += self._body_force_for_element(eidx)
        apply_structural_loads(F, self.submesh, dof_map, loads)
        for load in loads:
            if load.kind.lower() != 'point_force':
                continue
            target = load.target.lower()
            if target == 'all':
                local_ids = np.arange(self.submesh.points.shape[0], dtype=np.int64)
            else:
                gids = np.asarray(load.metadata.get('point_ids', []), dtype=np.int64)
                if gids.size == 0:
                    continue
                local_ids = np.asarray([
                    self.submesh.local_by_global[int(g)] for g in gids if int(g) in self.submesh.local_by_global
                ], dtype=np.int64)
            if local_ids.size == 0:
                continue
            value = np.asarray(load.values, dtype=float)[:3]
            for comp in range(min(3, value.size)):
                np.add.at(F, 3 * local_ids + comp, float(value[comp]))
        return F

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
            if kind not in {'displacement', 'rotation'}:
                continue
            node_ids = select_bc_nodes(self.submesh.points, bc)
            vals = np.asarray(bc.values, dtype=float) * scale
            for nid in node_ids:
                nid = int(nid)
                if kind == 'displacement':
                    for comp in bc.components:
                        fixed_dofs.append(3 * nid + int(comp))
                        fixed_values.append(float(vals[min(int(comp), len(vals) - 1)]))
                elif kind == 'rotation' and dof_map.has_rotation(nid):
                    rdofs = dof_map.rot_dofs(nid)
                    for comp in bc.components:
                        fixed_dofs.append(int(rdofs[int(comp)]))
                        fixed_values.append(float(vals[min(int(comp), len(vals) - 1)]))
        fixed_dofs_arr = np.asarray(fixed_dofs, dtype=np.int64)
        fixed_values_arr = np.asarray(fixed_values, dtype=float)
        if fixed_dofs_arr.size == 0:
            zmin_nodes = np.where(np.isclose(self.submesh.points[:, 2], self.submesh.points[:, 2].min()))[0]
            if zmin_nodes.size:
                fixed_dofs_arr = np.array([3 * int(zmin_nodes[0]), 3 * int(zmin_nodes[0]) + 1, 3 * int(zmin_nodes[0]) + 2], dtype=np.int64)
                fixed_values_arr = np.zeros(3, dtype=float)
        return fixed_dofs_arr, fixed_values_arr

    def _assemble_linear_continuum_response(
        self,
        du_step_trans: np.ndarray,
        base_states: list[list[MaterialState]],
        total_ndof: int,
        *,
        assemble_tangent: bool = True,
    ) -> tuple[Any, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray]:
        trans_ndof = int(self.submesh.points.shape[0] * 3)
        Fint = np.zeros(total_ndof, dtype=float)
        K_const = self._constant_continuum_K.to_csr() if hasattr(self._constant_continuum_K, 'to_csr') else self._constant_continuum_K
        K_base = K_const[:trans_ndof, :trans_ndof]
        Fint[:trans_ndof] = np.asarray(K_base @ du_step_trans, dtype=float)
        K = K_const if assemble_tangent else None

        trial_states: list[list[MaterialState]] = []
        cell_stress = np.zeros((self.submesh.elements.shape[0], 6), dtype=float)
        cell_yield = np.zeros(self.submesh.elements.shape[0], dtype=float)
        cell_eqp = np.zeros(self.submesh.elements.shape[0], dtype=float)

        for eidx in range(self.submesh.elements.shape[0]):
            edofs = self._element_edofs[eidx]
            ue = du_step_trans[edofs]
            D = self._linear_D[eidx]
            elem_states: list[MaterialState] = []
            stresses: list[np.ndarray] = []
            for gp_idx, (B, _detJ) in enumerate(self._gp_cache[eidx]):
                dstrain = B @ ue
                base = base_states[eidx][gp_idx]
                sigma = np.asarray(base.stress, dtype=float) + D @ dstrain
                elem_states.append(MaterialState(
                    stress=sigma,
                    strain=np.asarray(base.strain, dtype=float) + dstrain,
                    plastic_strain=base.plastic_strain.copy(),
                    internal=dict(base.internal),
                ))
                stresses.append(sigma)
            trial_states.append(elem_states)
            cell_stress[eidx] = np.mean(np.asarray(stresses, dtype=float), axis=0)
        return K, Fint, trial_states, cell_stress, cell_yield, cell_eqp

    def _assemble_generic_continuum_response(
        self,
        du_step_trans: np.ndarray,
        base_states: list[list[MaterialState]],
        total_ndof: int,
        *,
        assemble_tangent: bool = True,
    ) -> tuple[Any, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray]:
        use_sparse = bool(assemble_tangent and self._sp is not None and total_ndof >= 900)
        K = None if not assemble_tangent else (self._sp.csr_matrix((total_ndof, total_ndof), dtype=float) if use_sparse else np.zeros((total_ndof, total_ndof), dtype=float))
        Fint = np.zeros(total_ndof, dtype=float)
        trial_states: list[list[MaterialState]] = []
        cell_stress = np.zeros((self.submesh.elements.shape[0], 6), dtype=float)
        cell_yield = np.zeros(self.submesh.elements.shape[0], dtype=float)
        cell_eqp = np.zeros(self.submesh.elements.shape[0], dtype=float)
        data = np.empty((self.submesh.elements.shape[0] * 24 * 24,), dtype=float) if use_sparse else None
        cursor = 0

        for eidx in range(self.submesh.elements.shape[0]):
            edofs = self._element_edofs[eidx]
            ue = du_step_trans[edofs]
            mat = self.materials[eidx]
            Ke = np.zeros((24, 24), dtype=float)
            fe_int = np.zeros(24, dtype=float)
            elem_states: list[MaterialState] = []
            stresses: list[np.ndarray] = []
            yielded_count = 0
            eqp_vals: list[float] = []
            for gp_idx, (B, detJ) in enumerate(self._gp_cache[eidx]):
                dstrain = B @ ue
                new_state = mat.update(dstrain, base_states[eidx][gp_idx])
                sigma = np.asarray(new_state.stress, dtype=float)
                if assemble_tangent:
                    D = mat.tangent_matrix(new_state)
                    Ke += B.T @ D @ B * detJ
                fe_int += B.T @ sigma * detJ
                elem_states.append(new_state)
                stresses.append(sigma)
                yielded_count += 1 if bool(new_state.internal.get('yielded', False)) else 0
                eqp_vals.append(float(new_state.internal.get('eps_p_eq', new_state.internal.get('eps_p_shear', 0.0))))
            if assemble_tangent:
                if use_sparse:
                    assert data is not None
                    data[cursor: cursor + 24 * 24] = Ke.reshape(-1)
                    cursor += 24 * 24
                else:
                    K[np.ix_(edofs, edofs)] += Ke
            Fint[edofs] += fe_int
            trial_states.append(elem_states)
            cell_stress[eidx] = np.mean(np.asarray(stresses, dtype=float), axis=0)
            cell_yield[eidx] = yielded_count / max(1, len(elem_states))
            cell_eqp[eidx] = float(np.mean(eqp_vals)) if eqp_vals else 0.0

        if assemble_tangent and use_sparse:
            K = self._sp.coo_matrix((data if data is not None else np.empty((0,), dtype=float), (self._sparse_rows_template, self._sparse_cols_template)), shape=(total_ndof, total_ndof)).tocsr()
        return K, Fint, trial_states, cell_stress, cell_yield, cell_eqp

    def _assemble_continuum_response(
        self,
        du_step_trans: np.ndarray,
        base_states: list[list[MaterialState]],
        total_ndof: int,
        *,
        assemble_tangent: bool = True,
        compute_device: str = 'cpu',
        solver_metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray]:
        if self._all_linear_elastic and self._constant_continuum_K is not None:
            return self._assemble_linear_continuum_response(du_step_trans, base_states, total_ndof, assemble_tangent=assemble_tangent)
        warp_K, warp_Fint, warp_states, warp_cell_stress, warp_cell_yield, warp_cell_eqp, warp_info = try_warp_nonlinear_continuum_assembly(
            points=self.submesh.points,
            elements=self.submesh.elements,
            materials=self.materials,
            du_step_trans=du_step_trans,
            base_states=base_states,
            total_ndof=total_ndof,
            assemble_tangent=assemble_tangent,
            requested_device=str(compute_device),
            solver_metadata=solver_metadata,
            block_pattern=self._block_pattern,
        )
        if warp_states is not None and warp_Fint is not None and warp_cell_stress is not None and warp_cell_yield is not None and warp_cell_eqp is not None:
            return warp_K, warp_Fint, warp_states, warp_cell_stress, warp_cell_yield, warp_cell_eqp
        return self._assemble_generic_continuum_response(du_step_trans, base_states, total_ndof, assemble_tangent=assemble_tangent)

    def _evaluate_state(
        self,
        u_guess: np.ndarray,
        u_step_base: np.ndarray,
        base_states: list[list[MaterialState]],
        struct_K: np.ndarray | None,
        interfaces: list[InterfaceDefinition],
        local_interface_states: dict[str, list[InterfaceElementState]],
        ndof: int,
        n_nodes: int,
        *,
        assemble_tangent: bool = True,
    ) -> tuple[Any, np.ndarray, list[list[MaterialState]], np.ndarray, np.ndarray, np.ndarray, dict[str, list[InterfaceElementState]], list[str]]:
        warnings: list[str] = []
        du_step = u_guess - u_step_base
        Kc, Fint_c, trial_states, cell_stress, cell_yield, cell_eqp = self._assemble_continuum_response(
            du_step[: n_nodes * 3],
            base_states,
            ndof,
            assemble_tangent=assemble_tangent,
            compute_device=self._current_compute_device,
            solver_metadata=self._current_solver_metadata,
        )
        Fint = Fint_c.copy()
        K = Kc
        use_sparse = bool(assemble_tangent and self._sp is not None and K is not None and self._sp.issparse(K))
        trans_ndof = n_nodes * 3

        def _materialize_current() -> None:
            nonlocal K, use_sparse
            if K is not None and hasattr(K, 'to_csr'):
                K = K.to_csr()
            use_sparse = bool(assemble_tangent and self._sp is not None and K is not None and self._sp.issparse(K))

        if struct_K is not None:
            if isinstance(struct_K, StructuralHybridAssemblyResult):
                trans_vals = np.asarray(struct_K.trans_block_values, dtype=float)
                if trans_vals.size and np.any(np.abs(trans_vals) > 0.0):
                    Fint[:trans_ndof] += block_values_matvec(struct_K.pattern, trans_vals, u_guess[:trans_ndof], block_size=3, ndof=trans_ndof)
                    if assemble_tangent:
                        if hasattr(K, 'add_host_values') and bool(self._current_solver_metadata.get('warp_unified_block_merge', True)):
                            K = K.add_host_values(trans_vals)
                        else:
                            _materialize_current()
                            K = K + block_values_to_csr(struct_K.pattern, trans_vals, ndof=trans_ndof)
                tail_K = struct_K.tail_K
                tail_nnz = getattr(tail_K, 'nnz', None)
                has_tail = bool(tail_nnz) if tail_nnz is not None else bool(np.any(np.abs(np.asarray(tail_K, dtype=float)) > 0.0))
                if has_tail:
                    Fint += tail_K @ u_guess
                    if assemble_tangent:
                        _materialize_current()
                        K = K + tail_K
            else:
                if assemble_tangent and K is not None and hasattr(K, 'to_csr'):
                    _materialize_current()
                Fint += struct_K @ u_guess
                if assemble_tangent:
                    if use_sparse:
                        K = K + self._sp.csr_matrix(struct_K)
                    else:
                        K = K + struct_K

        iface_trial = _clone_interface_states(local_interface_states)
        if interfaces:
            u_nodes_guess = u_guess[: trans_ndof].reshape(n_nodes, 3)
            if hasattr(K, 'add_host_values') and bool(self._current_solver_metadata.get('warp_interface_enabled', False)):
                int_blk, iface_trial = assemble_interface_block_response(interfaces, self.submesh, u_nodes_guess, iface_trial, pattern=self._block_pattern)
                Fint[: trans_ndof] += int_blk.Fint
                warnings.extend(int_blk.warnings)
                if assemble_tangent and np.any(np.abs(int_blk.block_values) > 0.0):
                    K = K.add_host_values(int_blk.block_values)
            else:
                int_asm, iface_trial = assemble_interface_response(interfaces, self.submesh, u_nodes_guess, iface_trial)
                Fint[: trans_ndof] += int_asm.Fint
                warnings.extend(int_asm.warnings)
                if assemble_tangent:
                    _materialize_current()
                    if use_sparse:
                        K = K + self._sp.csr_matrix(int_asm.K)
                    else:
                        K[: trans_ndof, : trans_ndof] += int_asm.K
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
        struct_K: np.ndarray | None,
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
            if du.shape == trial.shape:
                trial[free] += alpha * du[free]
            elif du.shape == trial[free].shape:
                trial[free] += alpha * du
            else:
                raise ValueError(
                    f'Line-search increment size mismatch: du.shape={du.shape}, '
                    f'trial.shape={trial.shape}, free.shape={trial[free].shape}'
                )
            if fixed_dofs.size:
                trial[fixed_dofs] = fixed_values
            _, Fint, _, _, _, _, _, _ = self._evaluate_state(
                trial,
                u_step_base,
                base_states,
                struct_K,
                interfaces,
                local_interface_states,
                ndof,
                n_nodes,
                assemble_tangent=False,
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
        thread_count: int = 0,
        progress_callback=None,
        cancel_check=None,
        stage_name: str | None = None,
        solver_metadata: dict[str, Any] | None = None,
        compute_device: str = 'cpu',
    ) -> NonlinearSolveResult:
        n_nodes = self.submesh.points.shape[0]
        trans_ndof = n_nodes * 3
        warnings: list[str] = []
        convergence_history: list[dict[str, float | int | str]] = []
        solver_meta = dict(solver_metadata or {})
        self._current_compute_device = str(compute_device)
        self._current_solver_metadata = solver_meta
        solver_meta.setdefault('block_size', 3)
        solver_meta.setdefault('preconditioner', 'block-jacobi')
        solver_meta.setdefault('ordering', 'rcm')
        solver_meta.setdefault('warp_full_gpu_linear_solve', str(compute_device).lower().startswith('cuda'))
        linear_context = LinearSolverContext()
        if gp_states is None:
            gp_states = [[mat.create_state() for _ in range(len(GAUSS_POINTS))] for mat in self.materials]
        if interface_states is None:
            interface_states = {}
        structures = structures or []
        interfaces = interfaces or []
        solver_meta.setdefault('warp_interface_enabled', str(compute_device).lower().startswith('cuda'))
        solver_meta.setdefault('warp_structural_enabled', str(compute_device).lower().startswith('cuda'))
        solver_meta.setdefault('warp_unified_block_merge', True)

        pattern_parts: list[np.ndarray] = [np.asarray(self.submesh.elements, dtype=np.int32)]
        for iface in interfaces:
            pairs: list[list[int]] = []
            for sg, mg in zip(iface.slave_point_ids, iface.master_point_ids, strict=False):
                if int(sg) in self.submesh.local_by_global and int(mg) in self.submesh.local_by_global:
                    pairs.append([self.submesh.local_by_global[int(sg)], self.submesh.local_by_global[int(mg)]])
            if pairs:
                pattern_parts.append(np.asarray(pairs, dtype=np.int32))
        for item in structures:
            local_nodes = [self.submesh.local_by_global[int(g)] for g in item.point_ids if int(g) in self.submesh.local_by_global]
            if local_nodes:
                pattern_parts.append(np.asarray([local_nodes], dtype=np.int32))
        self._block_pattern = build_node_block_sparse_pattern(pattern_parts, n_nodes=n_nodes)

        dof_map = build_structural_dof_map(structures, self.submesh)
        ndof = dof_map.total_ndof
        if self._all_linear_elastic:
            cont_backend = self._ensure_constant_linear_continuum(
                ndof,
                prefer_sparse=prefer_sparse,
                compute_device=compute_device,
                solver_metadata=solver_meta,
            )
            if cont_backend.get('backend'):
                warnings.append(f"Linear-elastic continuum uses cached tangent backend: {cont_backend['backend']}.")
            warnings.extend([str(item) for item in cont_backend.get('warnings', [])])
        u_committed = np.zeros(ndof, dtype=float)
        F_total = self._build_external_force(loads, ndof, dof_map)

        if structures:
            if bool(solver_meta.get('warp_structural_enabled', False)):
                struct_asm = assemble_structural_hybrid_response(structures, self.submesh, dof_map=dof_map, pattern=self._block_pattern)
            else:
                struct_asm = assemble_structural_stiffness(structures, self.submesh, dof_map=dof_map)
            warnings.extend(struct_asm.warnings)
            F_total += struct_asm.F
            struct_K = struct_asm
        else:
            struct_K = None

        all_dofs = np.arange(ndof, dtype=np.int64)
        last_cell_stress = np.zeros((self.submesh.elements.shape[0], 6), dtype=float)
        last_yield = np.zeros(self.submesh.elements.shape[0], dtype=float)
        last_eqp = np.zeros(self.submesh.elements.shape[0], dtype=float)

        total_steps = max(1, int(n_steps))
        current_lambda = 0.0
        load_increment = 1.0 / total_steps
        cutbacks = 0
        step_id = 0
        nonlinear_iterations = max(1, int(max_iterations))

        def _emit_progress(payload: dict[str, Any]) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(dict(payload))
            except Exception:
                pass

        def _stage_fraction(lam_base: float, lam_goal: float, iteration_index: int = 0, phase_fraction: float = 0.0) -> float:
            increment = max(1.0e-12, float(lam_goal) - float(lam_base))
            if iteration_index <= 0:
                inner = max(0.0, min(0.99, float(phase_fraction)))
            else:
                inner = ((max(1, int(iteration_index)) - 1) + max(0.0, min(0.999, float(phase_fraction)))) / float(nonlinear_iterations)
            return min(0.999, max(float(lam_base), float(lam_base) + increment * inner))

        def _emit_phase(phase: str, message: str, *, lam_base: float | None = None, lam_goal: float | None = None, step: int | None = None, iteration: int | None = None, phase_fraction: float = 0.0, **extra: Any) -> None:
            payload: dict[str, Any] = {'phase': phase, 'message': message}
            if step is not None:
                payload['step'] = int(step)
            if iteration is not None:
                payload['iteration'] = int(iteration)
            if lam_goal is not None:
                payload['lambda'] = float(lam_goal)
            if lam_base is not None and lam_goal is not None:
                payload['fraction'] = _stage_fraction(lam_base, lam_goal, int(iteration or 0), phase_fraction)
            payload.update(extra)
            _emit_progress(payload)

        _emit_phase('solver-setup', f'Preparing nonlinear solver: nodes={n_nodes}, cells={self.submesh.elements.shape[0]}, dof={ndof}, device={compute_device}', lam_base=0.0, lam_goal=1.0, phase_fraction=0.01)

        while current_lambda < 1.0 - 1.0e-12:
            if cancel_check and cancel_check():
                warnings.append('Solve canceled by user.')
                break
            lam_target = min(1.0, current_lambda + load_increment)
            step_id += 1
            _emit_phase('step-start', f'Starting nonlinear load step {step_id}/{total_steps} at lambda={lam_target:.4f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.02, load_increment=float(load_increment))
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
                if it == 1 and step_id == 1 and str(compute_device).lower().startswith('cuda'):
                    _emit_phase('gpu-prepare', 'Preparing GPU nonlinear kernels / first-launch cache. The first iteration may take longer.', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.01)
                _emit_phase('iteration-start', f'Iteration {it} started', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.02)
                _emit_phase('assembly-start', 'Assembling continuum/interface response', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.05)
                assembly_started = time.perf_counter()
                K, Fint, trial_states, cell_stress, cell_yield, cell_eqp, iface_trial, iter_warnings = self._evaluate_state(
                    u_guess,
                    u_step_base,
                    base_states,
                    struct_K,
                    interfaces,
                    iface_base,
                    ndof,
                    n_nodes,
                    assemble_tangent=True,
                )
                assembly_seconds = time.perf_counter() - assembly_started
                warnings.extend(iter_warnings)
                _emit_phase('assembly-done', f'Assembly finished in {assembly_seconds:.2f}s', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.32, assembly_seconds=float(assembly_seconds), warning_count=len(iter_warnings))
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
                    'fraction': _stage_fraction(current_lambda, lam_target, it, 0.40),
                    'message': f'Nonlinear iteration {it}: ratio={metric:.3e}',
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
                    _emit_phase('step-converged', f'Step {step_id} converged at iteration {it} with ratio={metric:.3e}', lam_base=max(0.0, current_lambda - max(load_increment, 1.0e-12)), lam_goal=current_lambda, step=step_id, iteration=it, phase_fraction=0.99, ratio=float(metric))
                    if it <= 3 and load_increment < 0.5:
                        load_increment = min(1.0 - current_lambda, load_increment * 1.25)
                    break
                if free.size == 0:
                    break
                gpu_block_ok = hasattr(K, 'to_csr') and bool(solver_meta.get('warp_full_gpu_linear_solve', False))
                _emit_phase('linear-solve-start', 'Solving linearized system', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.48, gpu_block=bool(gpu_block_ok))
                linear_started = time.perf_counter()
                if gpu_block_ok:
                    try:
                        du_full, solve_info = solve_linear_system(
                            K,
                            residual,
                            prefer_sparse=prefer_sparse,
                            thread_count=thread_count,
                            assume_symmetric=True,
                            context=linear_context,
                            metadata=solver_meta,
                            block_size=3,
                            compute_device=compute_device,
                            fixed_dofs=fixed_dofs,
                            fixed_values=fixed_values,
                        )
                        du_full = np.asarray(du_full, dtype=float).reshape(-1)
                        if du_full.size != residual.size:
                            raise ValueError(f'full-system solve returned size {du_full.size}, expected {residual.size}')
                        du_free = du_full[free]
                    except Exception as exc:
                        warnings.append(f'GPU full-system linear solve fallback: {exc}')
                        gpu_block_ok = False
                if not gpu_block_ok:
                    if self._sp is not None and getattr(self._sp, 'issparse', lambda *_: False)(K):
                        Kff = K[free][:, free]
                    else:
                        Kff = K[np.ix_(free, free)]
                    du_free, solve_info = solve_linear_system(
                        Kff,
                        residual[free],
                        prefer_sparse=prefer_sparse,
                        thread_count=thread_count,
                        assume_symmetric=None if interfaces else True,
                        context=linear_context,
                        metadata=solver_meta,
                        block_size=3,
                        compute_device=compute_device,
                    )
                    du_full = np.zeros_like(u_guess)
                    du_full[free] = du_free
                linear_seconds = time.perf_counter() - linear_started
                _emit_phase('linear-solve-done', f'Linear solve finished in {linear_seconds:.2f}s using {solve_info.backend}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.78, linear_backend=str(solve_info.backend), linear_seconds=float(linear_seconds))
                warnings.extend(solve_info.warnings)
                convergence_history[-1]['linear_backend'] = solve_info.backend
                if line_search:
                    _emit_phase('line-search-start', 'Running line search', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.82)
                    ls_started = time.perf_counter()
                    u_next, alpha = self._line_search(
                        u_guess,
                        du_full,
                        free,
                        fixed_dofs,
                        fixed_values,
                        target,
                        rnorm,
                        u_step_base,
                        base_states,
                        struct_K,
                        interfaces,
                        iface_base,
                        ndof,
                        n_nodes,
                    )
                    ls_seconds = time.perf_counter() - ls_started
                    _emit_phase('line-search-done', f'Line search finished in {ls_seconds:.2f}s with alpha={alpha:.2f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.94, line_search_alpha=float(alpha), line_search_seconds=float(ls_seconds))
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
                    _emit_phase('cutback', f'Cutback triggered; retrying step with increment={load_increment:.4f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.98, load_increment=float(load_increment))
                    step_id -= 1
                    continue
                warnings.append(f'Nonlinear solve stopped without convergence at lambda={lam_target:.4f}; best ratio={best_metric:.3e}.')
                _emit_phase('step-stopped', f'Step {step_id} stopped without convergence; best ratio={best_metric:.3e}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.99, ratio=float(best_metric))
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
