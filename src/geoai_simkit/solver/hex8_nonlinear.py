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
from geoai_simkit.solver.warp_hex8 import build_block_sparse_pattern, build_node_block_sparse_pattern, block_values_matvec, block_values_to_csr, block_values_to_dense, resolve_warp_hex8_config, try_warp_hex8_linear_assembly
from geoai_simkit.solver.warp_nonlinear import try_warp_nonlinear_continuum_assembly
from geoai_simkit.validation_rules import normalize_boundary_target, normalize_load_kind


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
    convergence_advice: list[str] = field(default_factory=list)
    step_control_trace: list[dict[str, float | int | str]] = field(default_factory=list)
    converged: bool = True
    completed_lambda: float = 1.0
    total_steps_taken: int = 0



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


def _build_stage_failure_advice(
    *,
    stage_name: str,
    solver_meta: dict[str, Any],
    completed_lambda: float,
    best_metric: float,
    total_steps_taken: int,
    cutbacks: int,
    convergence_history: list[dict[str, float | int | str]],
    warnings: list[str],
) -> list[str]:
    advice: list[str] = []
    hist = list(convergence_history or [])
    ratios = [float(entry.get('ratio')) for entry in hist if isinstance(entry, dict) and 'ratio' in entry and np.isfinite(float(entry.get('ratio', np.inf)))]
    alphas = [float(entry.get('line_search_alpha')) for entry in hist if isinstance(entry, dict) and 'line_search_alpha' in entry and np.isfinite(float(entry.get('line_search_alpha', 1.0)))]
    linear_backends = {str(entry.get('linear_backend')).lower() for entry in hist if isinstance(entry, dict) and entry.get('linear_backend')}
    initial_increment = float(solver_meta.get('initial_increment', 0.1) or 0.1)
    min_increment = float(solver_meta.get('min_load_increment', max(1.0e-4, initial_increment * 0.1)) or max(1.0e-4, initial_increment * 0.1))
    line_search_enabled = bool(solver_meta.get('line_search', True))

    if completed_lambda < 0.25:
        advice.append(
            f"Stage '{stage_name}' stopped very early (lambda={completed_lambda:.3f}). Split this construction stage into smaller sub-stages or reduce initial_increment from {initial_increment:.3f} to about {max(min_increment, initial_increment * 0.5):.3f}."
        )
    if cutbacks >= max(2, int(solver_meta.get('max_cutbacks', 4)) // 2):
        advice.append(
            f"This stage triggered {cutbacks} cutbacks. Reduce the first load fraction and keep max_load_fraction_per_step near {max(min_increment, initial_increment * 0.5):.3f}."
        )
    if ratios:
        last_ratio = ratios[-1]
        if len(ratios) >= 3 and last_ratio > max(float(solver_meta.get('tolerance', 1.0e-4)) * 5.0, 1.0e-6):
            recent = ratios[-3:]
            if min(recent) > 0.0 and last_ratio >= min(recent) * 0.98:
                advice.append(
                    "Residual reduction stagnated over the last few iterations. Check whether the excavation / activation map really changes between stages and whether the current material parameters are too soft or too strong for the chosen increment size."
                )
    if line_search_enabled and alphas and min(alphas) <= 1.0e-3:
        advice.append(
            "Line search collapsed to a very small alpha. Reduce the initial increment, keep line search enabled, and consider a lower over_relaxation_factor (about 0.7 to 0.9)."
        )
    if any('stagnation' in str(w).lower() for w in warnings):
        advice.append(
            "Stagnation was detected. Verify support conditions, stage activation / deactivation, and interface strength reduction before forcing more GPU iterations."
        )
    if any('non-finite' in str(w).lower() for w in warnings):
        advice.append(
            "A non-finite residual appeared. Check for missing restraints, near-zero stiffness materials, or unrealistic water / surcharge jumps within this stage."
        )
    if any('dense' in backend for backend in linear_backends):
        advice.append(
            "The stage used a dense linear backend during part of the solve. For small models this can still be fine, but if convergence is poor try the 'cpu-safe' compute profile first to isolate constitutive issues from GPU control-flow overhead."
        )
    unique: list[str] = []
    seen: set[str] = set()
    for item in advice:
        key = item.strip().lower()
        if key and key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


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
                progress_callback=getattr(self, "_progress_callback", None),
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
            if normalize_load_kind(load.kind) != 'point_force':
                continue
            target = normalize_boundary_target(load.target)
            if target == 'all':
                local_ids = np.arange(self.submesh.points.shape[0], dtype=np.int64)
            else:
                gids = np.asarray(load.metadata.get('point_ids', []), dtype=np.int64)
                if gids.size == 0:
                    continue
                point_id_space = str(load.metadata.get('point_id_space', 'global')).strip().lower()
                if point_id_space == 'global':
                    local_ids = np.asarray([
                        self.submesh.local_by_global[int(g)] for g in gids if int(g) in self.submesh.local_by_global
                    ], dtype=np.int64)
                else:
                    local_ids = np.asarray(gids, dtype=np.int64)
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
            node_ids = select_bc_nodes(self.submesh.points, bc, local_by_global=self.submesh.local_by_global)
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

        def _materialize_current(force_dense: bool = False) -> None:
            nonlocal K, use_sparse
            if K is not None and hasattr(K, 'to_csr'):
                if force_dense or self._sp is None:
                    K = block_values_to_dense(K.pattern, K.host_values(), ndof=int(getattr(K, 'ndof', trans_ndof)))
                else:
                    K = K.to_csr()
            use_sparse = bool(assemble_tangent and self._sp is not None and K is not None and self._sp.issparse(K))

        if struct_K is not None:
            if isinstance(struct_K, StructuralHybridAssemblyResult):
                trans_vals = np.asarray(struct_K.trans_block_values, dtype=float)
                if trans_vals.size and np.any(np.abs(trans_vals) > 0.0):
                    Fint[:trans_ndof] += block_values_matvec(struct_K.pattern, trans_vals, u_guess[:trans_ndof], block_size=3, ndof=trans_ndof)
                    if assemble_tangent:
                        if hasattr(K, 'add_host_values') and bool(self._current_solver_metadata.get('warp_unified_block_merge', True)) and int(getattr(K, 'ndof', trans_ndof)) == trans_ndof:
                            K = K.add_host_values(trans_vals)
                        else:
                            if self._sp is not None:
                                _materialize_current()
                                K = K + block_values_to_csr(struct_K.pattern, trans_vals, ndof=trans_ndof)
                            else:
                                _materialize_current(force_dense=True)
                                K[:trans_ndof, :trans_ndof] += block_values_to_dense(struct_K.pattern, trans_vals, ndof=trans_ndof)
                tail_K = struct_K.tail_K
                tail_nnz = getattr(tail_K, 'nnz', None)
                has_tail = bool(tail_nnz) if tail_nnz is not None else bool(np.any(np.abs(np.asarray(tail_K, dtype=float)) > 0.0))
                if has_tail:
                    Fint += tail_K @ u_guess
                    if assemble_tangent:
                        if self._sp is not None:
                            _materialize_current()
                            K = K + tail_K
                        else:
                            _materialize_current(force_dense=True)
                            K = K + np.asarray(tail_K, dtype=float)
            elif isinstance(struct_K, StructuralAssemblyResult):
                dense_K = np.asarray(struct_K.K, dtype=float)
                if dense_K.ndim == 2 and dense_K.size:
                    Fint += dense_K @ u_guess
                    if assemble_tangent:
                        if use_sparse:
                            _materialize_current()
                            K = K + self._sp.csr_matrix(dense_K)
                        else:
                            K = K + dense_K
            else:
                dense_K = np.asarray(struct_K, dtype=float)
                if dense_K.ndim == 2 and dense_K.size:
                    if assemble_tangent and K is not None and hasattr(K, 'to_csr'):
                        _materialize_current()
                    Fint += dense_K @ u_guess
                    if assemble_tangent:
                        if use_sparse:
                            K = K + self._sp.csr_matrix(dense_K)
                        else:
                            K = K + dense_K

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
        progress_hook=None,
    ) -> tuple[np.ndarray, float, list[str]]:
        alpha = 1.0
        best_u = u_guess.copy()
        best_metric = rnorm0
        warnings: list[str] = []
        solver_meta = getattr(self, '_current_solver_metadata', {}) or {}
        step_tol = float(solver_meta.get('line_search_step_tol', 1.0e-12))
        eval_limit = float(solver_meta.get('line_search_eval_limit_seconds', 12.0))
        du_free = du[free] if du.shape == u_guess.shape else np.asarray(du, dtype=float)
        if du_free.size == 0 or float(np.linalg.norm(du_free)) <= step_tol:
            warnings.append('Line search skipped because the increment norm is negligible.')
            return best_u, 0.0, warnings
        started = time.perf_counter()
        for ls_iter in range(max_iter):
            if callable(progress_hook):
                try:
                    progress_hook(ls_iter + 1, max_iter, alpha)
                except Exception:
                    pass
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
            if time.perf_counter() - started >= eval_limit:
                warnings.append(f'Line search watchdog reached {eval_limit:.1f}s; keeping the best trial and continuing.')
                break
        return best_u, alpha, warnings

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
        initial_u_nodes: np.ndarray | None = None,
        initial_rotations: np.ndarray | None = None,
    ) -> NonlinearSolveResult:
        n_nodes = self.submesh.points.shape[0]
        trans_ndof = n_nodes * 3
        warnings: list[str] = []
        convergence_history: list[dict[str, float | int | str]] = []
        solver_meta = dict(solver_metadata or {})
        self._current_compute_device = str(compute_device)
        self._progress_callback = progress_callback
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
        solver_meta.setdefault('stage_state_sync', True)
        solver_meta.setdefault('line_search_max_iter', 3 if str(compute_device).lower().startswith('cuda') else 6)
        solver_meta.setdefault('modified_newton_max_reuse', 2 if str(compute_device).lower().startswith('cuda') else 1)
        solver_meta.setdefault('modified_newton_ratio_threshold', 0.35 if str(compute_device).lower().startswith('cuda') else 0.2)
        solver_meta.setdefault('modified_newton_min_improvement', 0.15)
        solver_meta.setdefault('adaptive_increment', True)
        solver_meta.setdefault('target_iterations', 6 if str(compute_device).lower().startswith('cuda') else 5)
        solver_meta.setdefault('target_iteration_band_low', 4)
        solver_meta.setdefault('target_iteration_band_high', 8 if str(compute_device).lower().startswith('cuda') else 7)
        solver_meta.setdefault('increment_growth', 1.35 if str(compute_device).lower().startswith('cuda') else 1.25)
        solver_meta.setdefault('increment_shrink', 0.55 if str(compute_device).lower().startswith('cuda') else 0.65)
        solver_meta.setdefault('line_search_trigger_ratio', 0.65)
        solver_meta.setdefault('line_search_correction_ratio', 0.18)
        solver_meta.setdefault('displacement_tolerance_ratio', 5.0e-3)
        solver_meta.setdefault('predictor_enabled', True)
        solver_meta.setdefault('strict_accuracy', False)
        solver_meta.setdefault('log_solver_phases', True)
        if not bool(solver_meta.get('strict_accuracy', False)) and str(solver_meta.get('compute_profile', '')).lower() in {'gpu-throughput', 'gpu-fullpath'} and tolerance < 1.0e-8:
            warnings.append(f'Relaxing overly strict tolerance from {tolerance:.1e} to 1.0e-7 for throughput-oriented nonlinear solving.')
            tolerance = 1.0e-7

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
        if initial_u_nodes is not None:
            init_u = np.asarray(initial_u_nodes, dtype=float).reshape(-1, 3)
            if init_u.shape[0] == n_nodes:
                u_committed[:trans_ndof] = init_u.reshape(-1)
        if initial_rotations is not None:
            init_r = np.asarray(initial_rotations, dtype=float).reshape(-1, 3)
            if init_r.shape[0] == n_nodes:
                for nid in range(n_nodes):
                    if dof_map.has_rotation(nid):
                        rdofs = dof_map.rot_dofs(nid)
                        u_committed[np.asarray(rdofs, dtype=np.int64)] = init_r[nid]
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
        configured_initial_increment = float(solver_meta.get('initial_increment', max(1.0 / float(total_steps), 1.0e-3)))
        nonlinear_iterations = max(1, int(max_iterations))
        min_load_increment = float(solver_meta.get('min_load_increment', max(1.0e-4, min(1.0e-3, configured_initial_increment * 0.25))))
        max_load_fraction_per_step = float(solver_meta.get('max_load_fraction_per_step', max(configured_initial_increment, 1.0 / float(total_steps))))
        load_increment = min(max_load_fraction_per_step, max(min_load_increment, configured_initial_increment))
        cutbacks = 0
        step_id = 0
        adaptive_increment = bool(solver_meta.get('adaptive_increment', True))
        increment_growth = float(solver_meta.get('increment_growth', 1.25))
        increment_shrink = float(solver_meta.get('increment_shrink', 0.75))
        target_iterations = max(2, int(solver_meta.get('target_iterations', 6)))
        target_iteration_band_low = max(1, int(solver_meta.get('target_iteration_band_low', max(2, target_iterations - 2))))
        target_iteration_band_high = max(target_iteration_band_low + 1, int(solver_meta.get('target_iteration_band_high', target_iterations + 2)))
        line_search_trigger_ratio = float(solver_meta.get('line_search_trigger_ratio', 0.65))
        line_search_correction_ratio = float(solver_meta.get('line_search_correction_ratio', 0.18))
        displacement_tolerance_ratio = float(solver_meta.get('displacement_tolerance_ratio', 5.0e-3))
        predictor_enabled = bool(solver_meta.get('predictor_enabled', True))
        max_total_steps = int(solver_meta.get('max_total_steps', max(total_steps * max(4, max_cutbacks + 1), total_steps + 24)))
        stagnation_patience = max(2, int(solver_meta.get('stagnation_patience', 3)))
        stagnation_improvement_tol = float(solver_meta.get('stagnation_improvement_tol', 0.03))
        abort_on_step_failure = bool(solver_meta.get('abort_on_step_failure', True))
        phase_timing_rows: list[dict[str, float | int | str]] = []
        solve_aborted = False
        abort_reason = ''
        previous_step_delta = np.zeros(ndof, dtype=float)
        previous_step_increment = 0.0
        converged_iteration_history: list[int] = []
        successful_increment_history: list[float] = []
        step_control_trace: list[dict[str, float | int | str]] = []

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
            if bool(solver_meta.get('log_solver_phases', True)) and phase in {'solver-setup', 'stage-sync', 'step-start', 'assembly-start', 'assembly-done', 'linear-solve-start', 'linear-solve-done', 'line-search-start', 'line-search-done', 'cutback', 'efficiency-note', 'step-converged', 'step-stopped', 'reuse-tangent', 'tolerance-relaxed'}:
                payload['log'] = True
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

        _emit_phase('solver-setup', f'Preparing nonlinear solver: nodes={n_nodes}, cells={self.submesh.elements.shape[0]}, dof={ndof}, device={compute_device}, tol={tolerance:.1e}, max_iter={nonlinear_iterations}, initial_increment={configured_initial_increment:.3f}, min_increment={min_load_increment:.1e}, max_increment={max_load_fraction_per_step:.3f}, max_total_steps={max_total_steps}', lam_base=0.0, lam_goal=1.0, phase_fraction=0.01)
        if any('Relaxing overly strict tolerance' in str(w) for w in warnings):
            _emit_phase('tolerance-relaxed', warnings[-1], lam_base=0.0, lam_goal=1.0, phase_fraction=0.015)
        if np.linalg.norm(u_committed) > 0.0 and bool(solver_meta.get('stage_state_sync', True)):
            _emit_phase('stage-sync', 'Synchronized committed displacement / state from previous stage', lam_base=0.0, lam_goal=1.0, phase_fraction=0.02, sync_norm=float(np.linalg.norm(u_committed)))

        while current_lambda < 1.0 - 1.0e-12:
            if cancel_check and cancel_check():
                warnings.append('Solve canceled by user.')
                break
            if step_id >= max_total_steps:
                solve_aborted = True
                abort_reason = f'Maximum nonlinear step budget reached ({max_total_steps}) at lambda={current_lambda:.4f}; stopping to avoid an endless cutback loop.'
                warnings.append(abort_reason)
                _emit_phase('step-stopped', abort_reason, lam_base=current_lambda, lam_goal=max(current_lambda, min(1.0, current_lambda + load_increment)), step=step_id, phase_fraction=0.99, ratio=float(np.inf), log=True)
                break
            lam_target = min(1.0, current_lambda + load_increment)
            step_id += 1
            history_target = float(np.mean(converged_iteration_history[-3:])) if converged_iteration_history else float(target_iterations)
            _emit_phase('step-start', f'Starting nonlinear load step {step_id}/{total_steps} at lambda={lam_target:.4f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.02, load_increment=float(load_increment), target_iteration_history=float(history_target))
            fixed_dofs, fixed_values = self._dirichlet_data(bcs, scale=lam_target, dof_map=dof_map)
            free = np.setdiff1d(all_dofs, fixed_dofs)
            base_states = _clone_gp_states(gp_states)
            iface_base = _clone_interface_states(interface_states)
            u_step_base = u_committed.copy()
            u_guess = u_step_base.copy()
            if predictor_enabled and previous_step_increment > 1.0e-12 and np.any(previous_step_delta):
                predictor_scale = float((lam_target - current_lambda) / max(previous_step_increment, 1.0e-12))
                u_guess = u_step_base + predictor_scale * previous_step_delta
            if fixed_dofs.size:
                u_guess[fixed_dofs] = fixed_values
            target = F_total * lam_target
            best_metric = np.inf
            best_u = u_guess.copy()
            best_states = base_states
            best_iface = iface_base
            converged = False
            prev_metric = np.inf
            tangent_cache = None
            tangent_reuse_left = 0
            iteration_metrics: list[float] = []
            step_failure_reason = ''

            for it in range(1, max(1, max_iterations) + 1):
                if cancel_check and cancel_check():
                    warnings.append('Solve canceled by user.')
                    break
                if it == 1 and step_id == 1 and str(compute_device).lower().startswith('cuda'):
                    _emit_phase('gpu-prepare', 'Preparing GPU nonlinear kernels / first-launch cache. The first iteration may take longer.', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.01)
                assemble_tangent = True
                if tangent_cache is not None and tangent_reuse_left > 0:
                    assemble_tangent = False
                    _emit_phase('reuse-tangent', f'Reusing tangent matrix for iteration {it} (remaining reuse budget={tangent_reuse_left})', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.03, reuse_budget=int(tangent_reuse_left))
                _emit_phase('iteration-start', f'Iteration {it} started', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.02)
                _emit_phase('assembly-start', 'Assembling continuum/interface response', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.05, assemble_tangent=bool(assemble_tangent))
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
                    assemble_tangent=assemble_tangent,
                )
                if not assemble_tangent:
                    K = tangent_cache
                else:
                    tangent_cache = K
                assembly_seconds = time.perf_counter() - assembly_started
                warnings.extend(iter_warnings)
                phase_timing_rows.append({'stage': stage_name or '', 'step': step_id, 'iteration': it, 'phase': 'assembly', 'seconds': float(assembly_seconds), 'tangent_reused': int(not assemble_tangent)})
                _emit_phase('assembly-done', f'Assembly finished in {assembly_seconds:.2f}s ({"reuse" if not assemble_tangent else "rebuild"})', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.32, assembly_seconds=float(assembly_seconds), warning_count=len(iter_warnings), tangent_reused=int(not assemble_tangent))
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
                _emit_phase('iteration-metric', f'Iteration {it}: residual ratio={metric:.3e}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.40, ratio=float(metric), residual_norm=float(rnorm), force_norm=float(fnorm), log=True)
                iteration_metrics.append(float(metric))
                if not np.isfinite(metric):
                    step_failure_reason = f'Non-finite residual ratio detected at step {step_id}, iteration {it}; forcing cutback.'
                    warnings.append(step_failure_reason)
                    _emit_phase('step-stagnation', step_failure_reason, lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.41, ratio=float(metric), log=True)
                    break
                if len(iteration_metrics) >= stagnation_patience + 1 and metric > max(tolerance * 5.0, 1.0e-10):
                    recent = np.asarray(iteration_metrics[-(stagnation_patience + 1):], dtype=float)
                    baseline = float(np.min(recent[:-1]))
                    if baseline > 0.0 and metric >= baseline * (1.0 - stagnation_improvement_tol):
                        step_failure_reason = (
                            f'Stagnation detected at step {step_id}, iteration {it}: ratio={metric:.3e}, '
                            f'best_recent={baseline:.3e}. Triggering cutback / stop.'
                        )
                        warnings.append(step_failure_reason)
                        _emit_phase('step-stagnation', step_failure_reason, lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.42, ratio=float(metric), log=True)
                        break
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
                    proposed_increment = load_increment
                    control_reason = 'hold'
                    converged_iteration_history.append(int(it))
                    successful_increment_history.append(float(load_increment))
                    hist_window = converged_iteration_history[-4:]
                    avg_iters = float(np.mean(hist_window)) if hist_window else float(it)
                    avg_increment = float(np.mean(successful_increment_history[-4:])) if successful_increment_history else float(load_increment)
                    if adaptive_increment:
                        if it <= max(2, target_iteration_band_low - 1) and metric < max(tolerance * 0.25, 1.0e-8):
                            growth_factor = max(1.05, min(1.6, increment_growth * (target_iterations / max(1.0, avg_iters))))
                            proposed_increment = min(1.0 - current_lambda, max_load_fraction_per_step, max(avg_increment, load_increment) * growth_factor)
                            control_reason = 'grow-fast-convergence'
                        elif it <= target_iteration_band_low and avg_iters <= float(target_iteration_band_low):
                            proposed_increment = min(1.0 - current_lambda, max_load_fraction_per_step, max(avg_increment, load_increment) * min(1.35, increment_growth))
                            control_reason = 'grow-history'
                        elif it >= target_iteration_band_high or avg_iters >= float(target_iteration_band_high):
                            shrink_factor = max(0.2, min(0.95, increment_shrink * min(1.0, target_iterations / max(avg_iters, 1.0))))
                            proposed_increment = max(min_load_increment, min(max_load_fraction_per_step, min(avg_increment, load_increment) * shrink_factor))
                            control_reason = 'shrink-history'
                        else:
                            proposed_increment = min(1.0 - current_lambda, max_load_fraction_per_step, max(min_load_increment, load_increment))
                    elif it <= 3 and load_increment < 0.5:
                        proposed_increment = min(1.0 - current_lambda, load_increment * 1.25)
                        control_reason = 'grow-basic'
                    load_increment = max(min_load_increment, min(max_load_fraction_per_step, proposed_increment))
                    trace_entry = {
                        'stage': stage_name or '',
                        'step': int(step_id),
                        'lambda': float(current_lambda),
                        'completed_lambda': float(lam_target),
                        'iterations': int(it),
                        'next_increment': float(load_increment),
                        'previous_increment': float(successful_increment_history[-1]),
                        'control_reason': control_reason,
                        'average_iterations': float(avg_iters),
                    }
                    step_control_trace.append(trace_entry)
                    _emit_phase('step-control', f'Adaptive step control selected next increment={load_increment:.4f} ({control_reason})', lam_base=max(0.0, current_lambda - max(successful_increment_history[-1], 1.0e-12)), lam_goal=current_lambda, step=step_id, iteration=it, phase_fraction=0.995, next_increment=float(load_increment), average_iterations=float(avg_iters), control_reason=control_reason, log=True)
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
                phase_timing_rows.append({'stage': stage_name or '', 'step': step_id, 'iteration': it, 'phase': 'linear-solve', 'seconds': float(linear_seconds), 'backend': str(solve_info.backend)})
                _emit_phase('linear-solve-done', f'Linear solve finished in {linear_seconds:.2f}s using {solve_info.backend}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.78, linear_backend=str(solve_info.backend), linear_seconds=float(linear_seconds))
                warnings.extend(solve_info.warnings)
                convergence_history[-1]['linear_backend'] = solve_info.backend
                improvement = 0.0 if not np.isfinite(prev_metric) or prev_metric <= 0.0 else max(0.0, (prev_metric - metric) / max(prev_metric, 1.0e-12))
                skip_line_search = bool(line_search and (np.linalg.norm(du_free) <= 1.0e-10 or metric < float(solver_meta.get('modified_newton_ratio_threshold', 0.35)) or improvement >= 0.35))
                if line_search and not skip_line_search:
                    _emit_phase('line-search-start', 'Running line search', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.82)
                    ls_started = time.perf_counter()
                    u_next, alpha, ls_warnings = self._line_search(
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
                        max_iter=int(self._current_solver_metadata.get('line_search_max_iter', 3 if str(self._current_compute_device).lower().startswith('cuda') else 6)),
                        progress_hook=lambda ls_iter, ls_total, ls_alpha: _emit_phase('line-search-trial', f'Line search trial {ls_iter}/{ls_total} alpha={ls_alpha:.3f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=min(0.93, 0.82 + 0.1 * (ls_iter / max(1, ls_total))), line_search_trial=int(ls_iter), line_search_total=int(ls_total), line_search_alpha=float(ls_alpha)),
                    )
                    ls_seconds = time.perf_counter() - ls_started
                    warnings.extend(ls_warnings)
                    phase_timing_rows.append({'stage': stage_name or '', 'step': step_id, 'iteration': it, 'phase': 'line-search', 'seconds': float(ls_seconds), 'alpha': float(alpha)})
                    _emit_phase('line-search-done', f'Line search finished in {ls_seconds:.2f}s with alpha={alpha:.2f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.94, line_search_alpha=float(alpha), line_search_seconds=float(ls_seconds), line_search_warning_count=len(ls_warnings))
                    convergence_history[-1]['line_search_alpha'] = float(alpha)
                    u_guess = u_next
                else:
                    if line_search:
                        _emit_phase('line-search-done', 'Line search skipped because the Newton update already looks acceptable.', lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.90, line_search_alpha=1.0, skipped=True)
                        convergence_history[-1]['line_search_alpha'] = 1.0
                    u_guess[free] += du_free
                    alpha = 1.0
                if fixed_dofs.size:
                    u_guess[fixed_dofs] = fixed_values
                if line_search and alpha <= 1.0e-3 and metric > max(tolerance * 10.0, 1.0e-6):
                    step_failure_reason = (
                        f'Line search collapsed to alpha={alpha:.3e} at step {step_id}, iteration {it} with ratio={metric:.3e}; '
                        'forcing cutback / stop.'
                    )
                    warnings.append(step_failure_reason)
                    _emit_phase('step-stagnation', step_failure_reason, lam_base=current_lambda, lam_goal=lam_target, step=step_id, iteration=it, phase_fraction=0.95, ratio=float(metric), line_search_alpha=float(alpha), log=True)
                    break
                improvement_for_reuse = 0.0 if not np.isfinite(prev_metric) or prev_metric <= 0.0 else max(0.0, (prev_metric - metric) / max(prev_metric, 1.0e-12))
                if metric < float(solver_meta.get('modified_newton_ratio_threshold', 0.35)) or improvement_for_reuse >= float(solver_meta.get('modified_newton_min_improvement', 0.15)):
                    tangent_reuse_left = max(0, int(solver_meta.get('modified_newton_max_reuse', 0)))
                else:
                    tangent_reuse_left = 0
                if not assemble_tangent and tangent_reuse_left > 0:
                    tangent_reuse_left -= 1
                prev_metric = metric

            if not converged:
                can_cutback = cutbacks < max_cutbacks and load_increment > min_load_increment + 1.0e-12
                if can_cutback:
                    cutbacks += 1
                    load_increment = max(min_load_increment, min(max_load_fraction_per_step, load_increment * 0.5))
                    reason_text = step_failure_reason or f'Nonlinear step did not converge at lambda={lam_target:.4f}; retrying with increment={load_increment:.4f}.'
                    warnings.append(reason_text)
                    step_control_trace.append({
                        'stage': stage_name or '',
                        'step': int(step_id),
                        'lambda': float(current_lambda),
                        'attempted_lambda': float(lam_target),
                        'iterations': int(max(1, len(iteration_metrics))),
                        'next_increment': float(load_increment),
                        'control_reason': 'cutback',
                        'best_ratio': float(best_metric),
                    })
                    _emit_phase('cutback', f'Cutback triggered; retrying step with increment={load_increment:.4f}', lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.98, load_increment=float(load_increment), reason=reason_text, ratio=float(best_metric), log=True)
                    step_id -= 1
                    continue
                stop_reason = step_failure_reason or f'Nonlinear step failed to converge at lambda={lam_target:.4f}; best ratio={best_metric:.3e}.'
                warnings.append(stop_reason)
                _emit_phase('step-stopped', stop_reason, lam_base=current_lambda, lam_goal=lam_target, step=step_id, phase_fraction=0.99, ratio=float(best_metric), log=True)
                u_committed = best_u
                gp_states = best_states
                interface_states = best_iface
                if abort_on_step_failure:
                    solve_aborted = True
                    abort_reason = stop_reason
                    break
                current_lambda = lam_target

        if phase_timing_rows:
            total_assembly = sum(float(r.get('seconds', 0.0)) for r in phase_timing_rows if r.get('phase') == 'assembly')
            total_linear = sum(float(r.get('seconds', 0.0)) for r in phase_timing_rows if r.get('phase') == 'linear-solve')
            total_ls = sum(float(r.get('seconds', 0.0)) for r in phase_timing_rows if r.get('phase') == 'line-search')
            warnings.append(f'Nonlinear timing summary: assembly={total_assembly:.2f}s, linear_solve={total_linear:.2f}s, line_search={total_ls:.2f}s.')
            _emit_phase('solver-summary', f'Nonlinear timing summary | assembly={total_assembly:.2f}s | linear={total_linear:.2f}s | line_search={total_ls:.2f}s', lam_base=current_lambda, lam_goal=max(current_lambda, 1.0), phase_fraction=0.995, log=True)
            convergence_history.extend(phase_timing_rows)
        u_nodes = u_committed[:trans_ndof].reshape(n_nodes, 3)
        structural_rot = dof_map.structural_rotation_field(n_nodes, u_committed)
        if solve_aborted and abort_reason:
            convergence_history.append({
                'stage': stage_name or '',
                'step': int(step_id),
                'lambda': float(current_lambda),
                'phase': 'aborted',
                'message': abort_reason,
            })
        convergence_advice = [] if ((not solve_aborted) and current_lambda >= 1.0 - 1.0e-9) else _build_stage_failure_advice(
            stage_name=str(stage_name or ''),
            solver_meta=solver_meta,
            completed_lambda=float(current_lambda),
            best_metric=float(best_metric if np.isfinite(best_metric) else np.inf),
            total_steps_taken=int(step_id),
            cutbacks=int(cutbacks),
            convergence_history=convergence_history,
            warnings=warnings,
        )
        for advice_text in convergence_advice:
            _emit_phase('solver-advice', advice_text, lam_base=current_lambda, lam_goal=max(current_lambda, 1.0), phase_fraction=0.997, log=True)
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
            convergence_advice=convergence_advice,
            step_control_trace=step_control_trace,
            converged=bool((not solve_aborted) and current_lambda >= 1.0 - 1.0e-9),
            completed_lambda=float(current_lambda),
            total_steps_taken=int(step_id),
        )
