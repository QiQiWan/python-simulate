from __future__ import annotations

from dataclasses import dataclass
from os import cpu_count

from geoai_simkit.runtime import CompileConfig, RuntimeConfig, SolverPolicy
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.gpu_runtime import detect_cuda_devices


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    profile: str
    device: str
    has_cuda: bool
    thread_count: int
    metadata: dict[str, object]
    note: str
    compile_config: CompileConfig
    runtime_config: RuntimeConfig
    solver_policy: SolverPolicy


def recommended_thread_count(*, hard_cap: int = 8) -> int:
    return max(1, min(int(hard_cap), int(cpu_count() or 1)))


def recommend_backend_route(
    *,
    execution_profile: str,
    device: str | None,
    partition_count: int | None,
    communicator_backend: str,
    backend_preference: str,
    native_compatibility_mode: str,
    stage_execution_diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    requested_profile = str(execution_profile or 'auto').strip().lower()
    requested_device = str(device or 'auto-best').strip().lower()
    partitions = max(1, int(partition_count or 1))
    has_cuda = bool(detect_cuda_devices()) and not requested_device.startswith('cpu')
    backend_preference = str(backend_preference or 'auto').strip().lower()
    native_compatibility_mode = str(native_compatibility_mode or 'auto').strip().lower()
    diagnostics = dict(stage_execution_diagnostics or {})
    native_supported = diagnostics.get('supported')
    reasons: list[str] = []
    if requested_profile in {'cpu-debug', 'cpu-robust'}:
        reasons.append('CPU-oriented execution profile prefers conservative host-side assembly paths.')
    if partitions > 1:
        reasons.append('Multiple partitions favour distributed/block-coupled execution paths.')
    if not has_cuda:
        reasons.append('CUDA-native execution is unavailable in the current environment.')
    if native_compatibility_mode == 'avoid-native':
        reasons.append('Native compatibility mode is explicitly disabled.')
    if native_supported is False:
        reasons.append('Stage execution diagnostics report that native stage execution is unsupported.')
    if backend_preference != 'auto':
        resolved_backend = backend_preference
        reasons.append('Routing respects the explicit backend preference.')
    elif requested_profile in {'cpu-debug', 'cpu-robust'} or not has_cuda or native_compatibility_mode == 'avoid-native' or native_supported is False:
        resolved_backend = 'linear-algebra-bridge' if partitions <= 1 else 'distributed'
    elif partitions > 1:
        resolved_backend = 'distributed'
    else:
        resolved_backend = 'native'
    effective_native_mode = native_compatibility_mode
    if resolved_backend in {'distributed', 'linear-algebra-bridge'} and native_compatibility_mode == 'auto':
        effective_native_mode = 'avoid-native'
    elif resolved_backend == 'native' and native_compatibility_mode == 'auto':
        effective_native_mode = 'prefer-native'
    recommended_backend_preference = resolved_backend
    recommended_communicator_backend = communicator_backend
    if resolved_backend == 'distributed' and communicator_backend == 'local' and partitions > 1:
        recommended_communicator_backend = 'thread'
        reasons.append('Thread communicator is recommended when the distributed path uses multiple local partitions.')
    recommendation_reason = reasons[0] if reasons else 'Current settings are already compatible with the preferred execution route.'
    return {
        'resolved_backend': resolved_backend,
        'recommended_backend_preference': recommended_backend_preference,
        'recommended_native_mode': effective_native_mode,
        'recommended_communicator_backend': recommended_communicator_backend,
        'native_supported': native_supported,
        'has_cuda': has_cuda,
        'partition_count': partitions,
        'profile': requested_profile,
        'device': requested_device or 'auto-best',
        'reasons': reasons,
        'recommendation_reason': recommendation_reason,
    }


def build_execution_plan(
    profile: str = 'auto',
    *,
    device: str | None = None,
    partition_count: int | None = None,
    communicator_backend: str = 'local',
    checkpoint_policy: str = 'stage-and-failure',
    checkpoint_dir: str | None = None,
    checkpoint_every_n_increments: int | None = None,
    checkpoint_keep_last_n: int | None = None,
    max_cutbacks: int | None = None,
    max_stage_retries: int | None = None,
    telemetry_level: str = 'standard',
    deterministic: bool = False,
    resume_checkpoint_id: str | None = None,
    backend_preference: str = 'auto',
    native_compatibility_mode: str = 'auto',
    nonlinear_policy: str = 'balanced',
    solver_strategy: str | None = None,
    preconditioner: str | None = None,
    nonlinear_max_iterations: int | None = None,
    tolerance: float | None = None,
    line_search: bool | None = None,
) -> ExecutionPlan:
    requested = str(profile or 'auto').strip().lower()
    if requested not in {'auto', 'cpu-robust', 'cpu-debug', 'gpu'}:
        requested = 'auto'
    requested_device = str(device or 'auto-best').strip().lower()
    has_cuda = bool(detect_cuda_devices())
    threads = recommended_thread_count()
    partitions = max(1, int(partition_count or 1))
    resolved_max_cutbacks = max(0, int(5 if max_cutbacks is None else max_cutbacks))
    resolved_max_stage_retries = max(0, int(0 if max_stage_retries is None else max_stage_retries))
    backend_preference = str(backend_preference or 'auto').strip().lower()
    if backend_preference not in {'auto', 'native', 'distributed', 'linear-algebra-bridge'}:
        backend_preference = 'auto'
    native_compatibility_mode = str(native_compatibility_mode or 'auto').strip().lower()
    if native_compatibility_mode not in {'auto', 'prefer-native', 'avoid-native'}:
        native_compatibility_mode = 'auto'
    nonlinear_policy = str(nonlinear_policy or 'balanced').strip().lower()
    if nonlinear_policy not in {'balanced', 'robust', 'aggressive'}:
        nonlinear_policy = 'balanced'

    def _policy_defaults(execution_profile: str) -> tuple[bool, str, str, int, float]:
        if nonlinear_policy == 'robust':
            return True, 'gmres', 'overlap_jacobi', 16, 1.0e-6
        if nonlinear_policy == 'aggressive':
            return False, 'cg', 'jacobi', 8, 5.0e-5
        if execution_profile in {'cpu-robust', 'cpu-debug'}:
            return True, 'cg', 'overlap_jacobi', 10, 1.0e-5
        return True, 'auto', 'auto', 12, 1.0e-5

    def _typed_configs(selected_device: str, *, compute_profile: str, execution_profile: str) -> tuple[CompileConfig, RuntimeConfig, SolverPolicy]:
        default_line_search, default_solver_strategy, default_preconditioner, default_iterations, default_tolerance = _policy_defaults(execution_profile)
        compile_config = CompileConfig(
            partition_count=partitions,
            partition_strategy='graph',
            numbering_strategy='contiguous-owned',
            enable_halo=True,
            enable_stage_masks=True,
            target_device_family='cuda' if str(selected_device).startswith('cuda') else 'cpu',
            metadata={
                'execution_profile': execution_profile,
                'backend_preference': backend_preference,
                'native_compatibility_mode': native_compatibility_mode,
            },
        )
        runtime_config = RuntimeConfig(
            backend='distributed',
            communicator_backend=communicator_backend,
            device_mode='single' if compile_config.partition_count == 1 else 'multi',
            partition_count=compile_config.partition_count,
            checkpoint_policy=checkpoint_policy,
            telemetry_level=telemetry_level,
            fail_policy='rollback-cutback',
            deterministic=bool(deterministic),
            metadata={
                'warp_device': selected_device,
                'compute_profile': compute_profile,
                'resume_checkpoint_id': None if not resume_checkpoint_id else str(resume_checkpoint_id),
                'checkpoint_dir': None if not checkpoint_dir else str(checkpoint_dir),
                'checkpoint_every_n_increments': (
                    None if checkpoint_every_n_increments is None else int(checkpoint_every_n_increments)
                ),
                'checkpoint_keep_last_n': (
                    None if checkpoint_keep_last_n is None else int(checkpoint_keep_last_n)
                ),
                'max_cutbacks': int(resolved_max_cutbacks),
                'max_stage_retries': int(resolved_max_stage_retries),
                'backend_preference': backend_preference,
                'native_compatibility_mode': native_compatibility_mode,
                'nonlinear_policy': nonlinear_policy,
            },
        )
        solver_policy = SolverPolicy(
            nonlinear_max_iterations=int(default_iterations if nonlinear_max_iterations is None else nonlinear_max_iterations),
            tolerance=float(default_tolerance if tolerance is None else tolerance),
            line_search=bool(default_line_search if line_search is None else line_search),
            max_cutbacks=int(min(resolved_max_cutbacks, 2) if execution_profile in {'cpu-robust', 'cpu-debug'} else resolved_max_cutbacks),
            preconditioner=str(default_preconditioner if preconditioner in {None, ''} else preconditioner),
            solver_strategy=str(default_solver_strategy if solver_strategy in {None, ''} else solver_strategy),
            metadata={
                'execution_profile': execution_profile,
                'backend_preference': backend_preference,
                'native_compatibility_mode': native_compatibility_mode,
                'nonlinear_policy': nonlinear_policy,
            },
        )
        return compile_config, runtime_config, solver_policy

    route_summary = recommend_backend_route(
        execution_profile=requested,
        device=requested_device,
        partition_count=partitions,
        communicator_backend=communicator_backend,
        backend_preference=backend_preference,
        native_compatibility_mode=native_compatibility_mode,
    )

    def _meta(compute_profile: str, execution_profile: str, note: str, **extra: object) -> dict[str, object]:
        payload: dict[str, object] = {
            'compute_profile': compute_profile,
            'execution_profile': execution_profile,
            'execution_note': note,
            'backend_preference': backend_preference,
            'native_compatibility_mode': native_compatibility_mode,
            'nonlinear_policy': nonlinear_policy,
            'backend_routing': dict(route_summary),
        }
        payload.update(extra)
        return payload

    if requested == 'gpu' and has_cuda and not requested_device.startswith('cpu'):
        meta = _meta('auto', 'gpu', 'Using the richer GPU-capable staged solver profile.', control_strategy='core-gated')
        selected_device = requested_device if requested_device != 'auto' else 'auto-best'
        compile_config, runtime_config, solver_policy = _typed_configs(selected_device, compute_profile='auto', execution_profile='gpu')
        return ExecutionPlan(profile='gpu', device=selected_device, has_cuda=True, thread_count=threads, metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    if requested == 'cpu-debug':
        meta = _meta('cpu-safe', 'cpu-debug', 'CPU debug profile disables Warp accelerated assembly paths to simplify diagnosis.', control_strategy='core-safe', warp_nonlinear_enabled=False, warp_hex8_enabled=False, warp_interface_enabled=False, warp_structural_enabled=False, warp_full_gpu_linear_solve=False)
        compile_config, runtime_config, solver_policy = _typed_configs('cpu', compute_profile='cpu-safe', execution_profile='cpu-debug')
        return ExecutionPlan(profile='cpu-debug', device='cpu', has_cuda=has_cuda, thread_count=min(4, threads), metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    if requested == 'cpu-robust' or not has_cuda or requested_device.startswith('cpu'):
        meta = _meta('cpu-safe', 'cpu-robust', 'CPU robust profile keeps the staged solve on conservative host-side assembly paths.', control_strategy='core-safe', warp_nonlinear_enabled=False, warp_hex8_enabled=False, warp_interface_enabled=False, warp_structural_enabled=False, warp_full_gpu_linear_solve=False)
        compile_config, runtime_config, solver_policy = _typed_configs('cpu', compute_profile='cpu-safe', execution_profile='cpu-robust')
        return ExecutionPlan(profile='cpu-robust', device='cpu', has_cuda=has_cuda, thread_count=threads, metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    meta = _meta('auto', 'gpu', 'CUDA was detected, so the default profile keeps GPU-oriented execution paths enabled.', control_strategy='core-gated')
    selected_device = requested_device if requested_device != 'auto' else 'auto-best'
    compile_config, runtime_config, solver_policy = _typed_configs(selected_device, compute_profile='auto', execution_profile='gpu')
    return ExecutionPlan(profile='gpu', device=selected_device, has_cuda=True, thread_count=threads, metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)


def build_solver_settings(
    profile: str = 'auto',
    *,
    device: str | None = None,
    prefer_sparse: bool = True,
    partition_count: int | None = None,
    communicator_backend: str = 'local',
    checkpoint_policy: str = 'stage-and-failure',
    checkpoint_dir: str | None = None,
    checkpoint_every_n_increments: int | None = None,
    checkpoint_keep_last_n: int | None = None,
    max_cutbacks: int | None = None,
    max_stage_retries: int | None = None,
    telemetry_level: str = 'standard',
    deterministic: bool = False,
    resume_checkpoint_id: str | None = None,
    backend_preference: str = 'auto',
    native_compatibility_mode: str = 'auto',
    nonlinear_policy: str = 'balanced',
    solver_strategy: str | None = None,
    preconditioner: str | None = None,
    nonlinear_max_iterations: int | None = None,
    tolerance: float | None = None,
    line_search: bool | None = None,
) -> SolverSettings:
    plan = build_execution_plan(
        profile=profile,
        device=device,
        partition_count=partition_count,
        communicator_backend=communicator_backend,
        checkpoint_policy=checkpoint_policy,
        checkpoint_dir=checkpoint_dir,
        checkpoint_every_n_increments=checkpoint_every_n_increments,
        checkpoint_keep_last_n=checkpoint_keep_last_n,
        max_cutbacks=max_cutbacks,
        max_stage_retries=max_stage_retries,
        telemetry_level=telemetry_level,
        deterministic=deterministic,
        resume_checkpoint_id=resume_checkpoint_id,
        backend_preference=backend_preference,
        native_compatibility_mode=native_compatibility_mode,
        nonlinear_policy=nonlinear_policy,
        solver_strategy=solver_strategy,
        preconditioner=preconditioner,
        nonlinear_max_iterations=nonlinear_max_iterations,
        tolerance=tolerance,
        line_search=line_search,
    )
    metadata = dict(plan.metadata)
    metadata.update(
        {
            'partition_count': int(plan.compile_config.partition_count),
            'partition_strategy': plan.compile_config.partition_strategy,
            'enable_halo': bool(plan.compile_config.enable_halo),
            'communicator_backend': plan.runtime_config.communicator_backend,
            'checkpoint_policy': plan.runtime_config.checkpoint_policy,
            'telemetry_level': plan.runtime_config.telemetry_level,
            'deterministic': bool(plan.runtime_config.deterministic),
            'resume_checkpoint_id': plan.runtime_config.metadata.get('resume_checkpoint_id'),
            'checkpoint_dir': plan.runtime_config.metadata.get('checkpoint_dir'),
            'checkpoint_every_n_increments': plan.runtime_config.metadata.get('checkpoint_every_n_increments'),
            'checkpoint_keep_last_n': plan.runtime_config.metadata.get('checkpoint_keep_last_n'),
            'max_cutbacks': plan.runtime_config.metadata.get('max_cutbacks'),
            'max_stage_retries': plan.runtime_config.metadata.get('max_stage_retries'),
            'line_search': bool(plan.solver_policy.line_search),
            'preconditioner': str(plan.solver_policy.preconditioner),
            'solver_strategy': str(plan.solver_policy.solver_strategy),
            'nonlinear_max_iterations': int(plan.solver_policy.nonlinear_max_iterations),
            'tolerance': float(plan.solver_policy.tolerance),
            'backend_preference': str(plan.metadata.get('backend_preference', backend_preference)),
            'native_compatibility_mode': str(plan.metadata.get('native_compatibility_mode', native_compatibility_mode)),
            'nonlinear_policy': str(plan.metadata.get('nonlinear_policy', nonlinear_policy)),
        }
    )
    if plan.profile in {'cpu-robust', 'cpu-debug'} and int(plan.compile_config.partition_count) > 1:
        metadata.setdefault('use_linear_algebra_bridge', True)
        metadata.setdefault('solver_backend_preference', 'linear-algebra-bridge')
        metadata.setdefault('prefer_sparse', True)
        metadata.setdefault('symmetric', True)
    return SolverSettings(
        prefer_sparse=bool(prefer_sparse),
        line_search=bool(plan.solver_policy.line_search),
        max_cutbacks=int(plan.solver_policy.max_cutbacks),
        max_iterations=int(plan.solver_policy.nonlinear_max_iterations),
        tolerance=float(plan.solver_policy.tolerance),
        device=plan.device,
        thread_count=int(plan.thread_count),
        metadata=metadata,
    )
