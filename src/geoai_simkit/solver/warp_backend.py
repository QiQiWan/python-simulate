from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from geoai_simkit.core.model import BoundaryCondition, SimulationModel
from geoai_simkit.core.types import ResultField
from geoai_simkit.geometry.mesh_adapter import add_region_arrays
from geoai_simkit.materials import MaterialState, registry
from geoai_simkit.solver.base import SolverBackend, SolverSettings
from geoai_simkit.solver.gpu_runtime import choose_cuda_device, detect_cuda_devices
from geoai_simkit.solver.hex8_linear import LinearRegionMaterial, extract_hex8_submesh, solve_linear_hex8, subset_hex8_submesh
from geoai_simkit.solver.tet4_linear import extract_tet4_submesh, solve_linear_tet4, subset_tet4_submesh
from geoai_simkit.solver.hex8_nonlinear import von_mises as nonlinear_von_mises
from geoai_simkit.solver.hex8_nonlinear import NonlinearHex8Solver
from geoai_simkit.solver.linear_algebra import configure_linear_algebra_threads
from geoai_simkit.solver.mesh_graph import build_point_adjacency
from geoai_simkit.solver.compute_preferences import apply_compute_profile_metadata
from geoai_simkit.solver.staging import StageManager
from geoai_simkit.utils import optional_import


@dataclass(slots=True)
class _MaterialEnvelope:
    stiffness: float
    poisson: float
    density: float
    strength_hint: float


class WarpBackend(SolverBackend):
    """Platform-oriented Warp backend starter.

    Current execution order:
    1. Try a real small-strain Hex8 linear solve path (NumPy assembly today; Warp-ready data flow)
    2. Fall back to the graph-relaxation placeholder for arbitrary imported meshes

    MC/HSS materials are currently reduced to elastic envelopes in the Hex8 path.
    This keeps the platform executable while preserving the plugin/data contracts
    needed for later Gauss-point constitutive integration.
    """

    def _ensure_warp(self):
        return optional_import("warp")

    def _material_envelopes(self, model: SimulationModel) -> dict[str, _MaterialEnvelope]:
        data: dict[str, _MaterialEnvelope] = {}
        for binding in model.materials:
            material = registry.create(binding.material_name, **binding.parameters)
            desc = material.describe()
            stiffness = float(desc.get("E") or desc.get("E50ref") or desc.get("Eurref") or 1.0e7)
            poisson = float(desc.get("nu") or desc.get("nu_ur") or 0.3)
            density = float(desc.get("rho") or 0.0)
            strength_hint = float(desc.get("cohesion") or desc.get("c") or 1.0e4)
            data[binding.region_name] = _MaterialEnvelope(
                stiffness=stiffness,
                poisson=poisson,
                density=density,
                strength_hint=strength_hint,
            )
        return data


    def _seed_geostatic_states(self, sub, mats, gravity) -> list[list[MaterialState]]:
        points = np.asarray(sub.points, dtype=float)
        if points.size == 0:
            return [[mat.create_state() for _ in range(8)] for mat in mats]
        top_z = float(np.max(points[:, 2]))
        gz = float(np.asarray(gravity, dtype=float).reshape(-1)[2]) if np.asarray(gravity).size >= 3 else -9.81
        gamma_g = abs(gz)
        seeded: list[list[MaterialState]] = []
        for idx, elem in enumerate(np.asarray(sub.elements, dtype=np.int64)):
            mat = mats[idx]
            base_state = mat.create_state()
            centroid_z = float(np.mean(points[np.asarray(elem, dtype=np.int64), 2]))
            depth = max(0.0, top_z - centroid_z)
            rho = float(getattr(mat, 'rho', 0.0) or 0.0)
            sigma_v = -rho * gamma_g * depth
            phi = float(getattr(mat, 'friction_deg', 0.0) or 0.0)
            if phi > 0.0:
                K0 = max(0.2, min(1.0, 1.0 - np.sin(np.deg2rad(phi))))
            else:
                nu = float(getattr(mat, 'nu', 0.3) or 0.3)
                K0 = max(0.2, min(1.0, nu / max(1.0 - nu, 1.0e-6)))
            stress = np.array([K0 * sigma_v, K0 * sigma_v, sigma_v, 0.0, 0.0, 0.0], dtype=float)
            strain = np.zeros(6, dtype=float)
            try:
                Ce = np.asarray(mat.tangent_matrix(base_state), dtype=float)
                if Ce.shape == (6, 6):
                    strain = np.linalg.solve(Ce + np.eye(6) * 1.0e-12, stress)
            except Exception:
                strain = np.zeros(6, dtype=float)
            elem_states: list[MaterialState] = []
            for _ in range(8):
                elem_states.append(MaterialState(
                    stress=stress.copy(),
                    strain=strain.copy(),
                    plastic_strain=np.zeros(6, dtype=float),
                    internal=dict(base_state.internal),
                ))
            seeded.append(elem_states)
        return seeded

    def _warp_has_cuda(self, wp) -> bool:
        checks = []
        for name in ("is_cuda_available", "cuda_available"):
            attr = getattr(wp, name, None)
            if callable(attr):
                checks.append(attr)
            elif isinstance(attr, bool):
                return bool(attr)
        for fn in checks:
            try:
                if fn():
                    return True
            except Exception:
                pass
        for name in ("get_cuda_devices", "get_devices"):
            fn = getattr(wp, name, None)
            if not callable(fn):
                continue
            try:
                devices = fn()
                for dev in devices:
                    if "cuda" in str(dev).lower() or "gpu" in str(dev).lower():
                        return True
            except Exception:
                pass
        return False

    def _select_runtime_device(self, wp, requested: str, *, round_robin_index: int = 0, allowed_devices: list[str] | None = None) -> str:
        requested = (requested or "auto-best").lower()
        try:
            has_cuda = self._warp_has_cuda(wp)
        except Exception:
            has_cuda = False
        if not has_cuda:
            chosen = 'cpu'
        else:
            chosen = choose_cuda_device(requested, round_robin_index=round_robin_index, allowed_devices=allowed_devices)
        setter = getattr(wp, "set_device", None)
        if callable(setter):
            try:
                setter(chosen)
            except Exception:
                pass
        return chosen

    @staticmethod
    def _emit_progress(progress_callback, payload: dict) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(dict(payload))
        except Exception:
            pass

    @staticmethod
    def _choose_stage_device(requested_device: str, metadata: dict, *, active_cells: int, active_dofs: int) -> tuple[str, str | None]:
        profile = str(metadata.get('compute_profile', 'auto')).lower()
        require_warp = bool(metadata.get('require_warp', False))
        adaptive_small = bool(metadata.get('adaptive_small_model_cpu', False))
        cell_limit = int(metadata.get('small_model_cpu_max_cells', 1800) or 1800)
        dof_limit = int(metadata.get('small_model_cpu_max_dofs', 18000) or 18000)
        if str(requested_device).lower().startswith('cuda') and profile == 'cpu-safe':
            return 'cpu', 'Stage requests the cpu-safe compute profile; forcing CPU execution for this stage.'
        if str(requested_device).lower().startswith('cuda') and adaptive_small and not require_warp and profile in {'auto', 'gpu-throughput'} and active_cells <= cell_limit and active_dofs <= dof_limit:
            return 'cpu', f"Adaptive policy switched this stage to CPU because active_cells={active_cells} and active_dofs={active_dofs} are below the efficient GPU threshold ({cell_limit} cells / {dof_limit} dofs)."
        return requested_device, (f"Model is relatively small (active_cells={active_cells}, active_dofs={active_dofs}); forcing full GPU path may underutilize the device." if str(requested_device).lower().startswith('cuda') and active_cells <= cell_limit and active_dofs <= dof_limit else None)

    @staticmethod
    def _average_gp_stress(states: list[list[MaterialState]]) -> np.ndarray:
        if not states:
            return np.empty((0, 6), dtype=float)
        out = np.zeros((len(states), 6), dtype=float)
        for idx, gp_states in enumerate(states):
            if gp_states:
                out[idx] = np.mean([np.asarray(s.stress, dtype=float) for s in gp_states], axis=0)
        return out

    def _seed_states_from_cell_stress(
        self,
        mats,
        cell_stress: np.ndarray,
        *,
        previous_states: list[list[MaterialState]] | None = None,
    ) -> list[list[MaterialState]]:
        seeded: list[list[MaterialState]] = []
        stress_arr = np.asarray(cell_stress, dtype=float)
        for idx, mat in enumerate(mats):
            template = None
            if previous_states is not None and idx < len(previous_states) and previous_states[idx]:
                template = previous_states[idx][0]
            else:
                template = mat.create_state()
            stress = stress_arr[idx].copy() if idx < len(stress_arr) else np.zeros(6, dtype=float)
            strain = np.zeros(6, dtype=float)
            try:
                Ce = np.asarray(mat.tangent_matrix(template), dtype=float)
                if Ce.shape == (6, 6):
                    strain = np.linalg.solve(Ce + np.eye(6) * 1.0e-12, stress)
            except Exception:
                strain = np.zeros(6, dtype=float)
            plastic = np.asarray(getattr(template, 'plastic_strain', np.zeros(6, dtype=float)), dtype=float).copy()
            internal = dict(getattr(template, 'internal', {}) or {})
            gp_states: list[MaterialState] = []
            for _ in range(8):
                gp_states.append(MaterialState(
                    stress=stress.copy(),
                    strain=strain.copy(),
                    plastic_strain=plastic.copy(),
                    internal=dict(internal),
                ))
            seeded.append(gp_states)
        return seeded

    @staticmethod
    def _classify_hex8_solver_mode(*, nonlinear_present: bool, nonlinear_stage_count: int, linearized_stage_count: int) -> str:
        if not nonlinear_present:
            return 'linear-hex8'
        if nonlinear_stage_count > 0 and linearized_stage_count > 0:
            return 'hybrid-staged-hex8'
        if nonlinear_stage_count > 0:
            return 'nonlinear-hex8'
        return 'staged-linearized-hex8'

    def solve(self, model: SimulationModel, settings: SolverSettings, progress_callback=None, cancel_check=None) -> SimulationModel:
        model.ensure_regions()
        backend_name = "placeholder-no-warp"
        selected_device = str(settings.device or settings.metadata.get('warp_device') or 'auto-best').lower()
        require_warp = bool(settings.metadata.get('require_warp', False) or str(settings.device or 'auto').lower().startswith('cuda'))
        try:
            wp = self._ensure_warp()
            if wp is None:
                raise RuntimeError('warp-lang is required but not installed')
            wp.init()
            rr_index = int(model.metadata.get('solve_sequence_index', 0)) if isinstance(model.metadata, dict) else 0
            selected_device = self._select_runtime_device(wp, settings.metadata.get('warp_device') or selected_device, round_robin_index=rr_index, allowed_devices=list(settings.metadata.get('allowed_gpu_devices', []) or []))
            backend_name = f"warp-{getattr(wp, '__version__', 'unknown')}-{selected_device}"
        except RuntimeError:
            wp = None
            if require_warp:
                raise
            if selected_device == 'auto':
                selected_device = 'cpu'

        effective_threads = configure_linear_algebra_threads(int(settings.thread_count))
        settings.thread_count = int(effective_threads)

        grid = model.to_unstructured_grid()
        self._emit_progress(progress_callback, {
            'phase': 'solver-setup',
            'message': f'Solver setup complete: backend={backend_name}, device={selected_device}, points={grid.n_points}, cells={grid.n_cells}, threads={settings.thread_count}',
            'backend': backend_name,
            'device': selected_device,
            'points': int(grid.n_points),
            'cells': int(grid.n_cells),
            'threads': int(settings.thread_count),
            'log': True,
        })
        if grid.n_points == 0:
            model.metadata["backend"] = backend_name
            model.metadata['compute_device'] = selected_device
            model.metadata['thread_count'] = int(settings.thread_count)
            return model

        for region in model.region_tags:
            add_region_arrays(grid, region.name, region.cell_ids)

        material_env = self._material_envelopes(model)
        stage_manager = StageManager(model)
        points0 = np.asarray(grid.points, dtype=float)
        x0 = points0.copy()
        total_u = np.zeros((grid.n_points, 3), dtype=float)
        stage_names: list[str] = []
        linear_assembly_info: dict[str, object] | None = None

        # Try true Hex8 path first
        hex_submesh = extract_hex8_submesh(grid)
        if hex_submesh.elements.size > 0:
            notes = []
            cell_region_map = self._cell_region_lookup(model, grid.n_cells)
            active_hex_mask = np.ones(hex_submesh.elements.shape[0], dtype=bool)
            cell_stress_full = np.zeros((grid.n_cells, 6), dtype=float)
            cell_vm_full = np.zeros(grid.n_cells, dtype=float)
            cell_yield_full = np.zeros(grid.n_cells, dtype=float)
            cell_eqp_full = np.zeros(grid.n_cells, dtype=float)
            material_types = self._material_types(model)
            nonlinear_present = any(mt in {"mohr_coulomb", "hss", "hs_small"} for mt in material_types.values()) or bool(model.structures) or bool(model.interfaces)
            gp_state_store: dict[int, list[MaterialState]] = {}
            interface_state_store: dict[str, list] = {}
            rot_full = np.zeros_like(total_u)
            linearized_stage_count = 0
            nonlinear_stage_count = 0
            stage_modes: dict[str, str] = {}
            solver_history_meta: dict[str, object] = {}
            step_control_meta: dict[str, object] = {}
            linear_solver_meta: dict[str, object] = {}
            linear_assembly_meta: dict[str, object] = {}
            failure_advice_meta: dict[str, list[str]] = {}
            locked_linearized_continuation = False

            stage_contexts = stage_manager.iter_stages()
            for stage_index, stage_ctx in enumerate(stage_contexts, start=1):
                if cancel_check and cancel_check():
                    model.metadata['solver_warnings'] = model.metadata.get('solver_warnings', []) + ['Solve canceled by user.']
                    break
                stage = stage_ctx.stage
                stage_names.append(stage.name)
                self._emit_progress(progress_callback, {'phase': 'stage-start', 'stage': stage.name, 'stage_index': stage_index, 'stage_count': len(stage_contexts), 'message': f'Starting stage {stage.name}', 'log': True})
                stage_bcs = tuple(model.boundary_conditions) + tuple(stage.boundary_conditions)
                stage_loads = tuple(stage.loads)
                active_hex_mask = np.array([
                    cell_region_map.get(int(full_cid), None) in stage_ctx.active_regions
                    for full_cid in hex_submesh.full_cell_ids
                ], dtype=bool)
                if not np.any(active_hex_mask):
                    notes.append(f"Stage '{stage.name}' had no active Hex8 cells; skipped solve.")
                    continue
                sub = subset_hex8_submesh(hex_submesh, active_hex_mask)
                active_stage_cells = int(sub.elements.shape[0])
                active_stage_dofs = int(sub.points.shape[0] * 3)
                stage_solver_meta = dict(settings.metadata)
                stage_solver_meta.update(dict(stage.metadata or {}))
                stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=str(selected_device).lower().startswith('cuda'))
                stage_device, stage_policy_note = self._choose_stage_device(selected_device, stage_solver_meta, active_cells=active_stage_cells, active_dofs=active_stage_dofs)
                stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=str(stage_device).lower().startswith('cuda'))
                self._emit_progress(progress_callback, {
                    'phase': 'stage-setup',
                    'stage': stage.name,
                    'stage_index': stage_index,
                    'stage_count': len(stage_contexts),
                    'message': f"Stage {stage.name}: active_cells={active_stage_cells}, active_points={sub.points.shape[0]}, active_dofs={active_stage_dofs}, compute_device={stage_device}",
                    'active_cells': active_stage_cells,
                    'active_dofs': active_stage_dofs,
                    'device': stage_device,
                    'log': True,
                })
                if stage_policy_note:
                    self._emit_progress(progress_callback, {
                        'phase': 'efficiency-note',
                        'stage': stage.name,
                        'stage_index': stage_index,
                        'stage_count': len(stage_contexts),
                        'message': stage_policy_note,
                        'device': stage_device,
                        'log': True,
                    })
                stage_started = __import__('time').perf_counter()
                control_profile = str(stage_solver_meta.get('control_strategy', 'commercial')).lower()
                stage_initial_increment = float(stage_solver_meta.get('initial_increment', max(1.0 / max(1, int(stage.steps or 1)), 1.0e-3)))
                stage_solver_meta.setdefault('initial_increment', stage_initial_increment)
                stage_solver_meta.setdefault('max_load_fraction_per_step', stage_initial_increment)
                if str(stage_solver_meta.get('demo_stage_workflow') or '').startswith('geostatic'):
                    stage_role_name = str(stage_solver_meta.get('stage_role') or stage.name).lower()
                    if stage_role_name == 'initial':
                        stage_solver_meta['compute_profile'] = 'cpu-safe'
                        stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=False)
                        stage_solver_meta['solver_strategy'] = 'direct'
                        stage_solver_meta['preconditioner'] = 'none'
                        stage_solver_meta['ordering'] = 'rcm'
                        stage_solver_meta['initial_increment'] = min(float(stage_solver_meta.get('initial_increment', stage_initial_increment) or stage_initial_increment), 0.0125)
                        stage_solver_meta['max_load_fraction_per_step'] = min(float(stage_solver_meta.get('max_load_fraction_per_step', stage_initial_increment) or stage_initial_increment), 0.0125)
                        stage_solver_meta['min_load_increment'] = min(float(stage_solver_meta.get('min_load_increment', 0.0015625) or 0.0015625), 0.0015625)
                        stage_solver_meta['max_iterations'] = max(int(stage_solver_meta.get('max_iterations', 32) or 32), 40)
                        stage_solver_meta['max_cutbacks'] = max(int(stage_solver_meta.get('max_cutbacks', 6) or 6), 8)
                        stage_initial_increment = float(stage_solver_meta['initial_increment'])
                    elif stage_role_name == 'wall_activation':
                        stage_solver_meta['compute_profile'] = 'cpu-safe'
                        stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=False)
                        stage_solver_meta['solver_strategy'] = 'direct'
                        stage_solver_meta['preconditioner'] = 'none'
                        stage_solver_meta['ordering'] = 'rcm'
                        stage_solver_meta['initial_increment'] = min(float(stage_solver_meta.get('initial_increment', stage_initial_increment) or stage_initial_increment), 0.00625)
                        stage_solver_meta['max_load_fraction_per_step'] = min(float(stage_solver_meta.get('max_load_fraction_per_step', stage_initial_increment) or stage_initial_increment), 0.00625)
                        stage_solver_meta['min_load_increment'] = min(float(stage_solver_meta.get('min_load_increment', 0.00078125) or 0.00078125), 0.00078125)
                        stage_solver_meta['max_iterations'] = max(int(stage_solver_meta.get('max_iterations', 40) or 40), 44)
                        stage_solver_meta['max_cutbacks'] = max(int(stage_solver_meta.get('max_cutbacks', 8) or 8), 10)
                        stage_initial_increment = float(stage_solver_meta['initial_increment'])
                stage_role_name = str(stage.metadata.get('stage_role') or stage.name).lower()
                geostatic_workflow = str(stage.metadata.get('demo_stage_workflow') or '').startswith('geostatic')
                allow_linearized_stage_fallback = bool(stage_solver_meta.get('allow_linearized_stage_fallback', geostatic_workflow))
                used_linearized_stage = False
                ran_nonlinear_stage = False
                stage_linear_assembly_info: dict[str, object] | None = None
                stage_result = None
                if nonlinear_present and control_profile in {'commercial', 'commercial-safe', 'auto'}:
                    stage_solver_meta.setdefault('adaptive_increment', True)
                    stage_solver_meta.setdefault('predictor_enabled', True)
                    stage_solver_meta.setdefault('target_iterations', 6)
                    stage_solver_meta.setdefault('target_iteration_band_low', 4)
                    stage_solver_meta.setdefault('target_iteration_band_high', 9)
                    stage_solver_meta.setdefault('increment_growth', 1.30)
                    stage_solver_meta.setdefault('increment_shrink', 0.60)
                    stage_solver_meta.setdefault('stagnation_patience', 2)
                    stage_solver_meta.setdefault('stagnation_improvement_tol', 0.02)
                    stage_solver_meta.setdefault('modified_newton_max_reuse', 2)
                    stage_solver_meta.setdefault('modified_newton_min_improvement', 0.10)
                    stage_solver_meta.setdefault('modified_newton_ratio_threshold', 0.30)
                    stage_solver_meta.setdefault('line_search_trigger_ratio', 0.70)
                    stage_solver_meta.setdefault('line_search_correction_ratio', 0.20)
                    stage_solver_meta.setdefault('line_search_max_iter', 4 if str(stage_device).lower().startswith('cuda') else 6)
                    stage_solver_meta.setdefault('max_cutbacks', max(6, int(stage_solver_meta.get('max_cutbacks', settings.max_cutbacks))))
                    stage_solver_meta.setdefault('min_load_increment', max(1.0e-4, stage_initial_increment * 0.125))
                    stage_solver_meta.setdefault('max_total_steps', max(int(stage.steps or 1) * 10, int(stage_solver_meta.get('max_total_steps', 0) or 0)))
                    stage_solver_meta.setdefault('abort_on_step_failure', True)
                    stage_solver_meta.setdefault('log_solver_phases', True)
                sticky_linearized_continuation = bool(stage_solver_meta.get('sticky_linearized_continuation_after_fallback', False))
                run_nonlinear_stage = bool(nonlinear_present and not locked_linearized_continuation)
                if run_nonlinear_stage:
                    mats = self._hex_material_models(sub.full_cell_ids, cell_region_map, model)
                    geostatic_seed = None
                    if not gp_state_store and stage_role_name == 'initial' and geostatic_workflow:
                        geostatic_seed = self._seed_geostatic_states(sub, mats, settings.gravity)
                        notes.append("Seeded initial geostatic stress field for the demo initial stage to avoid starting from a zero-stress continuum.")
                    state_store = [
                        [MaterialState(stress=s.stress.copy(), strain=s.strain.copy(), plastic_strain=s.plastic_strain.copy(), internal=dict(s.internal)) for s in gp_state_store.get(int(fid), (geostatic_seed[idx] if geostatic_seed is not None else [mats[idx].create_state() for _ in range(8)]))]
                        for idx, fid in enumerate(sub.full_cell_ids)
                    ]
                    geostatic_initialize = bool(geostatic_workflow and stage_role_name == 'initial' and not gp_state_store and str(stage_solver_meta.get('initial_state_strategy') or 'geostatic_seeded_linear').lower() == 'geostatic_seeded_linear')
                    if geostatic_initialize:
                        linear_mats = self._hex_materials(sub.full_cell_ids, cell_region_map, material_env)
                        u_local, cell_stress, cell_vm, stage_linear_assembly_info, _, _ = solve_linear_hex8(
                            sub,
                            linear_mats,
                            bcs=stage_bcs,
                            loads=stage_loads,
                            gravity=settings.gravity,
                            displacement_scale=1.0,
                            prefer_sparse=bool(settings.prefer_sparse),
                            thread_count=int(settings.thread_count),
                            compute_device='cpu',
                            solver_metadata=stage_solver_meta,
                            progress_callback=progress_callback,
                        )
                        rot_local = np.zeros_like(u_local)
                        used_linearized_stage = True
                        linearized_stage_count += 1
                        seeded_states = self._seed_states_from_cell_stress(mats, cell_stress, previous_states=state_store)
                        for local_idx, fid in enumerate(sub.full_cell_ids):
                            gp_state_store[int(fid)] = seeded_states[local_idx]
                        interface_state_store = {}
                        cell_yield_full[:] = 0.0
                        cell_eqp_full[:] = 0.0
                        stage_linear_assembly_info = dict(stage_linear_assembly_info or {})
                        stage_linear_assembly_info.setdefault('warnings', []).append('Initial geostatic demo stage used a linearized equilibrium solve seeded by geostatic stress.')
                        stage_modes[stage.name] = 'geostatic-seeded-linear'
                        self._emit_progress(progress_callback, {
                            'phase': 'stage-geostatic-init',
                            'stage': stage.name,
                            'stage_index': stage_index,
                            'stage_count': len(stage_contexts),
                            'message': 'Initialized the demo initial stage from a seeded geostatic stress field and solved a linearized equilibrium correction.',
                            'log': True,
                        })
                        class _GeostaticResult:
                            converged = True
                            completed_lambda = 1.0
                            total_steps_taken = 1
                            convergence_history = []
                            convergence_advice = []
                            warnings = []
                            step_control_trace = []
                            cell_yield_fraction = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                            cell_eq_plastic = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                        stage_result = _GeostaticResult()
                    else:
                        ran_nonlinear_stage = True
                        nonlinear_stage_count += 1
                        stage_modes[stage.name] = 'nonlinear'
                        def _stage_progress(entry):
                            if progress_callback is None:
                                return
                            payload = dict(entry)
                            payload.setdefault('stage', stage.name)
                            payload.setdefault('stage_index', stage_index)
                            payload.setdefault('stage_count', len(stage_contexts))
                            progress_callback(payload)
                        stage_result = NonlinearHex8Solver(sub, mats, gravity=settings.gravity).solve(
                            bcs=stage_bcs,
                            loads=stage_loads,
                            gp_states=state_store,
                            n_steps=stage.steps or max(4, settings.max_steps // 20),
                            max_iterations=int(stage_solver_meta.get("max_iterations", stage_solver_meta.get("max_nonlinear_iterations", settings.max_iterations))),
                            tolerance=float(stage_solver_meta.get("tolerance", settings.tolerance)),
                            structures=model.structures_for_stage(stage.name),
                            interfaces=model.interfaces_for_stage(stage.name),
                            interface_states=interface_state_store,
                            prefer_sparse=bool(settings.prefer_sparse),
                            line_search=bool(stage_solver_meta.get('line_search', settings.line_search)),
                            max_cutbacks=int(stage_solver_meta.get('max_cutbacks', settings.max_cutbacks)),
                            thread_count=int(settings.thread_count),
                            progress_callback=_stage_progress,
                            cancel_check=cancel_check,
                            stage_name=stage.name,
                            solver_metadata=stage_solver_meta,
                            compute_device=stage_device,
                            initial_u_nodes=total_u[sub.global_point_ids] if bool(settings.metadata.get('stage_state_sync', True)) else None,
                            initial_rotations=rot_full[sub.global_point_ids] if bool(settings.metadata.get('stage_state_sync', True)) else None,
                        )
                        u_local = stage_result.u_nodes
                        rot_local = stage_result.structural_rotations
                        cell_stress = stage_result.cell_stress
                        cell_vm = stage_result.von_mises
                        for local_idx, fid in enumerate(sub.full_cell_ids):
                            gp_state_store[int(fid)] = stage_result.gp_states[local_idx]
                        interface_state_store = stage_result.interface_states
                        notes.extend(stage_result.warnings)
                        if not stage_result.converged:
                            failure_note = (
                                f"Stage '{stage.name}' stopped at lambda={stage_result.completed_lambda:.4f} after {stage_result.total_steps_taken} load steps. "
                                "The solver kept the best converged state instead of continuing into an endless cutback loop."
                            )
                            notes.append(failure_note)
                            self._emit_progress(progress_callback, {
                                'phase': 'stage-failed',
                                'stage': stage.name,
                                'stage_index': stage_index,
                                'stage_count': len(stage_contexts),
                                'message': failure_note,
                                'lambda': float(stage_result.completed_lambda),
                                'log': True,
                            })
                            for advice in list(getattr(stage_result, 'convergence_advice', []) or []):
                                notes.append(f"[advice] {advice}")
                                self._emit_progress(progress_callback, {
                                    'phase': 'solver-advice',
                                    'stage': stage.name,
                                    'stage_index': stage_index,
                                    'stage_count': len(stage_contexts),
                                    'message': advice,
                                    'lambda': float(stage_result.completed_lambda),
                                    'log': True,
                                })
                            if geostatic_workflow and allow_linearized_stage_fallback:
                                linear_mats = self._hex_materials(sub.full_cell_ids, cell_region_map, material_env)
                                fallback_note = (
                                    f"Stage '{stage.name}' switched to a stabilized linearized Hex8 solve for this stage so the staged demo can keep advancing after a nonlinear stall."
                                )
                                notes.append(fallback_note)
                                self._emit_progress(progress_callback, {
                                    'phase': 'stage-fallback',
                                    'stage': stage.name,
                                    'stage_index': stage_index,
                                    'stage_count': len(stage_contexts),
                                    'message': fallback_note,
                                    'lambda': float(stage_result.completed_lambda),
                                    'log': True,
                                })
                                u_local, cell_stress, cell_vm, stage_linear_assembly_info, _, _ = solve_linear_hex8(
                                    sub,
                                    linear_mats,
                                    bcs=stage_bcs,
                                    loads=stage_loads,
                                    gravity=settings.gravity,
                                    displacement_scale=1.0,
                                    prefer_sparse=bool(settings.prefer_sparse),
                                    thread_count=int(settings.thread_count),
                                    compute_device='cpu',
                                    solver_metadata=stage_solver_meta,
                                    progress_callback=progress_callback,
                                )
                                rot_local = np.zeros_like(u_local)
                                seeded_states = self._seed_states_from_cell_stress(mats, cell_stress, previous_states=state_store)
                                for local_idx, fid in enumerate(sub.full_cell_ids):
                                    gp_state_store[int(fid)] = seeded_states[local_idx]
                                interface_state_store = {}
                                cell_yield_full[:] = 0.0
                                cell_eqp_full[:] = 0.0
                                used_linearized_stage = True
                                linearized_stage_count += 1
                                stage_modes[stage.name] = 'nonlinear+linearized-fallback'
                                if sticky_linearized_continuation:
                                    locked_linearized_continuation = True
                                stage_linear_assembly_info = dict(stage_linear_assembly_info or {})
                                stage_linear_assembly_info.setdefault('warnings', []).append('Nonlinear stage fallback engaged for this stage; continuum stresses were re-seeded from the stabilized linear solve before advancing.')
                                class _FallbackResult:
                                    converged = True
                                    completed_lambda = 1.0
                                    total_steps_taken = max(1, int(getattr(stage_result, 'total_steps_taken', 1) or 1))
                                    convergence_history = list(getattr(stage_result, 'convergence_history', []) or [])
                                    convergence_advice = list(getattr(stage_result, 'convergence_advice', []) or [])
                                    warnings = list(getattr(stage_result, 'warnings', []) or [])
                                    step_control_trace = list(getattr(stage_result, 'step_control_trace', []) or [])
                                    cell_yield_fraction = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                                    cell_eq_plastic = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                                stage_result = _FallbackResult()
                        cell_yield_full[:] = 0.0
                        cell_eqp_full[:] = 0.0
                        cell_yield_full[sub.full_cell_ids] = stage_result.cell_yield_fraction
                        cell_eqp_full[sub.full_cell_ids] = stage_result.cell_eq_plastic
                else:
                    mats = self._hex_materials(sub.full_cell_ids, cell_region_map, material_env)
                    u_local, cell_stress, cell_vm, stage_linear_assembly_info, _, _ = solve_linear_hex8(
                        sub,
                        mats,
                        bcs=stage_bcs,
                        loads=stage_loads,
                        gravity=settings.gravity,
                        displacement_scale=1.0,
                        prefer_sparse=bool(settings.prefer_sparse),
                        thread_count=int(settings.thread_count),
                        compute_device='cpu' if (nonlinear_present and geostatic_workflow and allow_linearized_stage_fallback) else stage_device,
                        solver_metadata=stage_solver_meta,
                        progress_callback=progress_callback,
                    )
                    rot_local = np.zeros_like(u_local)
                    if nonlinear_present:
                        used_linearized_stage = True
                        linearized_stage_count += 1
                        stage_modes[stage.name] = 'linearized-continuation'
                        cell_yield_full[:] = 0.0
                        cell_eqp_full[:] = 0.0
                    else:
                        stage_modes[stage.name] = 'linear'
                    class _LinearStageResult:
                        converged = True
                        completed_lambda = 1.0
                        total_steps_taken = max(1, int(stage.steps or 1))
                        convergence_history = []
                        convergence_advice = []
                        warnings = []
                        step_control_trace = []
                        cell_yield_fraction = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                        cell_eq_plastic = np.zeros(sub.full_cell_ids.shape[0], dtype=float)
                    stage_result = _LinearStageResult()
                    linear_solver_meta[stage.name] = (stage_linear_assembly_info or {}).get('linear_solver', 'numpy-dense')
                if nonlinear_present and bool(settings.metadata.get('stage_state_sync', True)):
                    total_u[sub.global_point_ids] = u_local
                    rot_full[sub.global_point_ids] = rot_local
                else:
                    du_full = np.zeros_like(total_u)
                    du_full[sub.global_point_ids] = u_local
                    total_u += du_full
                    rot_full = np.zeros_like(total_u)
                    if nonlinear_present:
                        rot_full[sub.global_point_ids] = rot_local
                cell_stress_full[:] = 0.0
                cell_vm_full[:] = 0.0
                cell_stress_full[sub.full_cell_ids] = cell_stress
                cell_vm_full[sub.full_cell_ids] = cell_vm
                model.add_result(ResultField(name="U", association="point", values=total_u.copy(), components=3, stage=stage.name))
                model.add_result(ResultField(name="U_mag", association="point", values=np.linalg.norm(total_u, axis=1), stage=stage.name))
                model.add_result(ResultField(name="stress", association="cell", values=cell_stress_full.copy(), components=6, stage=stage.name))
                model.add_result(ResultField(name="von_mises", association="cell", values=cell_vm_full.copy(), stage=stage.name))
                if nonlinear_present:
                    model.add_result(ResultField(name="R_struct", association="point", values=rot_full.copy(), components=3, stage=stage.name))
                    model.add_result(ResultField(name="yield_fraction", association="cell", values=cell_yield_full.copy(), stage=stage.name))
                    model.add_result(ResultField(name="eq_plastic", association="cell", values=cell_eqp_full.copy(), stage=stage.name))
                    solver_history_meta[stage.name] = list(getattr(stage_result, 'convergence_history', []) or [])
                    step_control_meta[stage.name] = list(getattr(stage_result, 'step_control_trace', []) or [])
                    advice_rows = list(getattr(stage_result, 'convergence_advice', []) or [])
                    if advice_rows:
                        failure_advice_meta[stage.name] = advice_rows
                    if ran_nonlinear_stage and solver_history_meta[stage.name]:
                        linear_solver_meta[stage.name] = solver_history_meta[stage.name][-1].get('linear_backend', 'unknown')
                    else:
                        linear_solver_meta.setdefault(stage.name, 'numpy-dense' if used_linearized_stage else 'unknown')
                else:
                    linear_solver_meta.setdefault(stage.name, (stage_linear_assembly_info or {}).get('linear_solver', 'numpy-dense'))
                if stage_linear_assembly_info is not None:
                    linear_assembly_meta[stage.name] = dict(stage_linear_assembly_info)
                stage_seconds = __import__('time').perf_counter() - stage_started
                self._emit_progress(progress_callback, {
                    'phase': 'stage-complete',
                    'stage': stage.name,
                    'stage_index': stage_index,
                    'stage_count': len(stage_contexts),
                    'message': f'Completed stage {stage.name} in {stage_seconds:.2f}s',
                    'stage_seconds': float(stage_seconds),
                    'device': stage_device,
                    'solver_mode': stage_modes.get(stage.name, 'unknown'),
                    'log': True,
                })
                if nonlinear_present and stage_result is not None and not getattr(stage_result, 'converged', True) and not used_linearized_stage:
                    break

            grid.point_data["U"] = total_u
            grid.point_data["U_mag"] = np.linalg.norm(total_u, axis=1)
            grid.cell_data["stress"] = cell_stress_full
            grid.cell_data["von_mises"] = cell_vm_full
            if nonlinear_present:
                grid.point_data["R_struct"] = rot_full
                grid.cell_data["yield_fraction"] = cell_yield_full
                grid.cell_data["eq_plastic"] = cell_eqp_full
            grid.point_data["X0"] = x0
            grid.point_data["Z0"] = x0[:, 2]
            grid.points = x0 + settings.displacement_scale * total_u
            model.mesh = grid
            model.metadata["backend"] = backend_name
            model.metadata['compute_device'] = selected_device
            model.metadata['thread_count'] = int(settings.thread_count)
            model.metadata["stages_run"] = stage_names
            model.metadata['stage_solver_modes'] = dict(stage_modes)
            if nonlinear_present:
                model.metadata['solver_history'] = dict(solver_history_meta)
                model.metadata['step_control_trace'] = dict(step_control_meta)
                if failure_advice_meta:
                    model.metadata['stage_failure_advice'] = dict(failure_advice_meta)
            model.metadata['linear_solver'] = dict(linear_solver_meta)
            if linear_assembly_meta:
                model.metadata['linear_element_assembly'] = dict(linear_assembly_meta)
            model.metadata["solver_mode"] = self._classify_hex8_solver_mode(
                nonlinear_present=nonlinear_present,
                nonlinear_stage_count=nonlinear_stage_count,
                linearized_stage_count=linearized_stage_count,
            )
            model.metadata['stage_state_sync'] = bool(settings.metadata.get('stage_state_sync', True))
            if nonlinear_present:
                if nonlinear_stage_count > 0 and linearized_stage_count > 0:
                    model.metadata["solver_note"] = (
                        "Executed a hybrid staged Hex8 workflow: the demo uses a seeded linear geostatic initialization and can apply stage-local linearized fallback when a nonlinear stage stalls, but later stages are still allowed to resume the nonlinear path from re-seeded continuum stresses."
                    )
                elif nonlinear_stage_count > 0:
                    model.metadata["solver_note"] = (
                        "Executed the Hex8 nonlinear incremental path with Gauss-point state updates, structural overlays, and node-pair interface contact/friction. "
                        "The current kernel uses a modified-Newton global loop, principal-space Mohr-Coulomb return updates, and HS-small-style stress-dependent stiffness. "
                        "True production features still pending include shell bending/rotations, mortar contact, rigorous MC corner treatment, and full HSsmall memory rules."
                    )
                else:
                    model.metadata["solver_note"] = (
                        "Executed the staged linearized Hex8 continuation path for the geostatic demo workflow. Nonlinear stages did not advance in this run, so the solver kept the stabilized linearized path for all active stages."
                    )
            else:
                model.metadata["solver_note"] = "Executed the small-strain Hex8 linear path."
            if nonlinear_present and nonlinear_stage_count > 0 and any('stopped at lambda=' in str(n) for n in notes) and model.metadata.get('solver_mode') == 'nonlinear-hex8':
                base_note = "Nonlinear stage stopped early because the current load increment could not converge reliably. The best converged state was kept and remaining stages were not advanced."
                advice_map = model.metadata.get('stage_failure_advice', {}) if isinstance(model.metadata, dict) else {}
                if isinstance(advice_map, dict):
                    for stage_name in reversed(stage_names):
                        if advice_map.get(stage_name):
                            base_note += " Suggested next actions: " + " | ".join(str(x) for x in advice_map.get(stage_name, [])[:3])
                            break
                model.metadata["solver_note"] = base_note
            if notes:
                model.metadata["solver_warnings"] = notes
            return model

        tet_submesh = extract_tet4_submesh(grid)
        celltypes = np.asarray(getattr(grid, 'celltypes', []), dtype=np.int32)
        pure_tet4_mesh = bool(celltypes.size) and bool(np.all(celltypes == 10))
        if pure_tet4_mesh and tet_submesh.elements.size > 0:
            notes = []
            cell_region_map = self._cell_region_lookup(model, grid.n_cells)
            material_types = self._material_types(model)
            nonlinear_present = any(mt in {"mohr_coulomb", "hss", "hs_small"} for mt in material_types.values())
            tet4_linear_only = (not nonlinear_present) and (not model.structures) and (not model.interfaces)
            if tet4_linear_only:
                active_tet_mask = np.ones(tet_submesh.elements.shape[0], dtype=bool)
                cell_stress_full = np.zeros((grid.n_cells, 6), dtype=float)
                cell_vm_full = np.zeros(grid.n_cells, dtype=float)

                stage_contexts = stage_manager.iter_stages()
                for stage_index, stage_ctx in enumerate(stage_contexts, start=1):
                    if cancel_check and cancel_check():
                        model.metadata['solver_warnings'] = model.metadata.get('solver_warnings', []) + ['Solve canceled by user.']
                        break
                    stage = stage_ctx.stage
                    stage_names.append(stage.name)
                    self._emit_progress(progress_callback, {'phase': 'stage-start', 'stage': stage.name, 'stage_index': stage_index, 'stage_count': len(stage_contexts), 'message': f'Starting stage {stage.name}', 'log': True})
                    stage_bcs = tuple(model.boundary_conditions) + tuple(stage.boundary_conditions)
                    stage_loads = tuple(stage.loads)
                    active_tet_mask = np.array([
                        cell_region_map.get(int(full_cid), None) in stage_ctx.active_regions
                        for full_cid in tet_submesh.full_cell_ids
                    ], dtype=bool)
                    if not np.any(active_tet_mask):
                        notes.append(f"Stage '{stage.name}' had no active Tet4 cells; skipped solve.")
                        continue
                    sub = subset_tet4_submesh(tet_submesh, active_tet_mask)
                    active_stage_cells = int(sub.elements.shape[0])
                    active_stage_dofs = int(sub.points.shape[0] * 3)
                    stage_solver_meta = dict(settings.metadata)
                    stage_solver_meta.update(dict(stage.metadata or {}))
                    stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=str(selected_device).lower().startswith('cuda'))
                    stage_device, stage_policy_note = self._choose_stage_device(selected_device, stage_solver_meta, active_cells=active_stage_cells, active_dofs=active_stage_dofs)
                    stage_solver_meta = apply_compute_profile_metadata(stage_solver_meta, cuda_available=str(stage_device).lower().startswith('cuda'))
                    self._emit_progress(progress_callback, {
                        'phase': 'stage-setup',
                        'stage': stage.name,
                        'stage_index': stage_index,
                        'stage_count': len(stage_contexts),
                        'message': f"Stage {stage.name}: active_cells={active_stage_cells}, active_points={sub.points.shape[0]}, active_dofs={active_stage_dofs}, compute_device=cpu (tet4 linear path)",
                        'active_cells': active_stage_cells,
                        'active_dofs': active_stage_dofs,
                        'device': 'cpu',
                        'log': True,
                    })
                    if stage_policy_note:
                        self._emit_progress(progress_callback, {
                            'phase': 'efficiency-note',
                            'stage': stage.name,
                            'stage_index': stage_index,
                            'stage_count': len(stage_contexts),
                            'message': stage_policy_note,
                            'device': 'cpu',
                            'log': True,
                        })
                    stage_started = __import__('time').perf_counter()
                    mats = self._hex_materials(sub.full_cell_ids, cell_region_map, material_env)
                    u_local, cell_stress, cell_vm, linear_assembly_info, _, _ = solve_linear_tet4(
                        sub,
                        mats,
                        bcs=stage_bcs,
                        loads=stage_loads,
                        gravity=settings.gravity,
                        displacement_scale=1.0,
                        prefer_sparse=bool(settings.prefer_sparse),
                        thread_count=int(settings.thread_count),
                        compute_device='cpu',
                        solver_metadata=stage_solver_meta,
                        progress_callback=progress_callback,
                    )
                    du_full = np.zeros_like(total_u)
                    du_full[sub.global_point_ids] = u_local
                    total_u += du_full
                    cell_stress_full[:] = 0.0
                    cell_vm_full[:] = 0.0
                    cell_stress_full[sub.full_cell_ids] = cell_stress
                    cell_vm_full[sub.full_cell_ids] = cell_vm
                    model.add_result(ResultField(name="U", association="point", values=total_u.copy(), components=3, stage=stage.name))
                    model.add_result(ResultField(name="U_mag", association="point", values=np.linalg.norm(total_u, axis=1), stage=stage.name))
                    model.add_result(ResultField(name="stress", association="cell", values=cell_stress_full.copy(), components=6, stage=stage.name))
                    model.add_result(ResultField(name="von_mises", association="cell", values=cell_vm_full.copy(), stage=stage.name))
                    stage_seconds = __import__('time').perf_counter() - stage_started
                    self._emit_progress(progress_callback, {
                        'phase': 'stage-complete',
                        'stage': stage.name,
                        'stage_index': stage_index,
                        'stage_count': len(stage_contexts),
                        'message': f'Completed stage {stage.name} in {stage_seconds:.2f}s',
                        'stage_seconds': float(stage_seconds),
                        'device': 'cpu',
                        'log': True,
                    })

                grid.point_data["U"] = total_u
                grid.point_data["U_mag"] = np.linalg.norm(total_u, axis=1)
                grid.cell_data["stress"] = cell_stress_full
                grid.cell_data["von_mises"] = cell_vm_full
                grid.point_data["X0"] = x0
                grid.point_data["Z0"] = x0[:, 2]
                grid.points = x0 + settings.displacement_scale * total_u
                model.mesh = grid
                model.metadata["backend"] = backend_name
                model.metadata['compute_device'] = 'cpu'
                model.metadata['thread_count'] = int(settings.thread_count)
                model.metadata["stages_run"] = stage_names
                if linear_assembly_info is not None and stage_names:
                    model.metadata.setdefault('linear_element_assembly', {})[stage_names[-1]] = linear_assembly_info
                model.metadata["solver_mode"] = "linear-tet4"
                model.metadata["solver_note"] = (
                    "Executed the small-strain Tet4 linear path. This iteration adds real tetrahedral continuum extraction, constant-strain element assembly, stage filtering, and linear solve support. "
                    "Nonlinear Tet4 constitutive updates, interface coupling, and structural overlays are still pending."
                )
                if notes:
                    model.metadata["solver_warnings"] = notes
                return model

            fallback_reason = 'Tet4 linear solver currently supports continuum linear-elastic stages only; nonlinear soils, structures, or interfaces will use the generic fallback path for now.'
            self._emit_progress(progress_callback, {
                'phase': 'efficiency-note',
                'message': fallback_reason,
                'device': 'cpu',
                'log': True,
            })

        # Generic fallback for arbitrary imported geometry
        indptr, neighbors = build_point_adjacency(grid)
        stage_contexts = stage_manager.iter_stages()
        for stage_index, stage_ctx in enumerate(stage_contexts, start=1):
            if cancel_check and cancel_check():
                model.metadata['solver_warnings'] = model.metadata.get('solver_warnings', []) + ['Solve canceled by user.']
                break
            stage = stage_ctx.stage
            steps = stage.steps or settings.max_steps
            if progress_callback is not None:
                try:
                    progress_callback({'phase': 'stage-start', 'stage': stage.name, 'stage_index': stage_index, 'stage_count': len(stage_contexts), 'message': f'Starting stage {stage.name}'})
                except Exception:
                    pass
            stage_scale = self._stage_scale(stage_ctx.active_regions, material_env)
            du = self._run_stage_relaxation_numpy(
                points0,
                indptr,
                neighbors,
                gravity=settings.gravity,
                stiffness_scale=stage_scale,
                steps=steps,
                dt=settings.dt,
            )
            total_u += du
            if progress_callback is not None:
                try:
                    progress_callback({'phase': 'stage-complete', 'stage': stage.name, 'stage_index': stage_index, 'stage_count': len(stage_contexts), 'message': f'Completed stage {stage.name}'})
                except Exception:
                    pass
            u_mag = np.linalg.norm(total_u, axis=1)
            stage_names.append(stage.name)
            model.add_result(ResultField(name="U", association="point", values=total_u.copy(), components=3, stage=stage.name))
            model.add_result(ResultField(name="U_mag", association="point", values=u_mag, stage=stage.name))

        grid.point_data["U"] = total_u
        grid.point_data["U_mag"] = np.linalg.norm(total_u, axis=1)
        grid.point_data["X0"] = x0
        grid.point_data["Z0"] = x0[:, 2]
        grid.points = x0 + settings.displacement_scale * total_u
        model.mesh = grid
        model.metadata["backend"] = backend_name
        model.metadata['compute_device'] = selected_device
        model.metadata['thread_count'] = int(settings.thread_count)
        model.metadata["stages_run"] = stage_names
        model.metadata["solver_mode"] = "graph-relaxation-fallback"
        if wp is None:
            model.metadata["solver_note"] = "Warp not installed; executed NumPy stage-relaxation starter backend."
        else:
            model.metadata["solver_note"] = "Warp initialized successfully; mesh was not Hex8-only, so the generic stage-relaxation fallback was used."
        return model

    def _cell_region_lookup(self, model: SimulationModel, n_cells: int) -> dict[int, str]:
        lut: dict[int, str] = {}
        for region in model.region_tags:
            for cid in np.asarray(region.cell_ids, dtype=np.int64):
                if 0 <= int(cid) < n_cells:
                    lut[int(cid)] = region.name
        return lut

    def _hex_materials(
        self,
        full_cell_ids: np.ndarray,
        cell_region_map: dict[int, str],
        envelopes: dict[str, _MaterialEnvelope],
    ) -> list[LinearRegionMaterial]:
        mats = []
        for cid in full_cell_ids:
            region = cell_region_map.get(int(cid), "default")
            env = envelopes.get(region, _MaterialEnvelope(stiffness=1.0e7, poisson=0.3, density=0.0, strength_hint=1.0e4))
            mats.append(LinearRegionMaterial(E=env.stiffness, nu=env.poisson, rho=env.density))
        return mats


    def _material_types(self, model: SimulationModel) -> dict[str, str]:
        return {binding.region_name: binding.material_name for binding in model.materials}

    def _hex_material_models(
        self,
        full_cell_ids: np.ndarray,
        cell_region_map: dict[int, str],
        model: SimulationModel,
    ) -> list:
        bindings = {binding.region_name: binding for binding in model.materials}
        mats = []
        for cid in full_cell_ids:
            region = cell_region_map.get(int(cid), "default")
            binding = bindings.get(region)
            if binding is None:
                mats.append(registry.create("linear_elastic", E=1.0e7, nu=0.3, rho=0.0))
            else:
                mats.append(registry.create(binding.material_name, **binding.parameters))
        return mats
    def _stage_scale(self, active_regions: set[str], envelopes: dict[str, _MaterialEnvelope]) -> float:
        active = [envelopes[r] for r in active_regions if r in envelopes]
        if not active:
            return 1.0
        mean_stiffness = sum(item.stiffness for item in active) / len(active)
        return max(mean_stiffness, 1.0) / 1.0e7

    def _run_stage_relaxation_numpy(
        self,
        points: np.ndarray,
        indptr: np.ndarray,
        neighbors: np.ndarray,
        gravity: tuple[float, float, float],
        stiffness_scale: float,
        steps: int,
        dt: float,
    ) -> np.ndarray:
        n = points.shape[0]
        u = np.zeros((n, 3), dtype=float)
        v = np.zeros((n, 3), dtype=float)
        g = np.asarray(gravity, dtype=float)
        z = points[:, 2]
        top = float(z.max()) if z.size else 0.0
        bottom = float(z.min()) if z.size else 0.0
        depth_weight = (top - z) / max(1e-9, top - bottom)
        damping = 0.92
        k = max(1e-6, stiffness_scale)
        fixed = np.where(np.isclose(z, bottom))[0]
        counts = np.diff(indptr).astype(np.float64)
        valid_rows = counts > 0
        if np.any(valid_rows):
            src = np.repeat(np.arange(n, dtype=np.int64), counts.astype(np.int64))
        else:
            src = np.empty((0,), dtype=np.int64)
        for _ in range(max(1, steps)):
            lap = np.zeros_like(u)
            if src.size:
                np.add.at(lap, src, u[neighbors])
                lap[valid_rows] = lap[valid_rows] / counts[valid_rows, None] - u[valid_rows]
            force = lap * k
            force[:, 2] += depth_weight * g[2] * 1e-4
            v = damping * v + dt * force
            u = u + dt * v
            u[fixed] = 0.0
            v[fixed] = 0.0
        return u
