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

    def _typed_configs(selected_device: str, *, compute_profile: str, execution_profile: str) -> tuple[CompileConfig, RuntimeConfig, SolverPolicy]:
        compile_config = CompileConfig(
            partition_count=partitions,
            partition_strategy='graph',
            numbering_strategy='contiguous-owned',
            enable_halo=True,
            enable_stage_masks=True,
            target_device_family='cuda' if str(selected_device).startswith('cuda') else 'cpu',
            metadata={'execution_profile': execution_profile},
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
                    None
                    if checkpoint_every_n_increments is None
                    else int(checkpoint_every_n_increments)
                ),
                'checkpoint_keep_last_n': (
                    None
                    if checkpoint_keep_last_n is None
                    else int(checkpoint_keep_last_n)
                ),
                'max_cutbacks': int(resolved_max_cutbacks),
                'max_stage_retries': int(resolved_max_stage_retries),
                },
        )
        solver_policy = SolverPolicy(
            nonlinear_max_iterations=12,
            tolerance=1.0e-5,
            line_search=True,
            max_cutbacks=int(resolved_max_cutbacks),
            preconditioner='auto',
            solver_strategy='auto',
            metadata={'execution_profile': execution_profile},
        )
        return compile_config, runtime_config, solver_policy

    if requested == 'gpu' and has_cuda and not requested_device.startswith('cpu'):
        meta: dict[str, object] = {'compute_profile': 'auto', 'control_strategy': 'commercial', 'execution_profile': 'gpu', 'execution_note': 'Using the richer GPU-capable staged solver profile.'}
        selected_device = requested_device if requested_device != 'auto' else 'auto-best'
        compile_config, runtime_config, solver_policy = _typed_configs(selected_device, compute_profile='auto', execution_profile='gpu')
        return ExecutionPlan(profile='gpu', device=selected_device, has_cuda=True, thread_count=threads, metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    if requested == 'cpu-debug':
        meta = {'compute_profile': 'cpu-safe', 'control_strategy': 'commercial-safe', 'warp_nonlinear_enabled': False, 'warp_hex8_enabled': False, 'warp_interface_enabled': False, 'warp_structural_enabled': False, 'warp_full_gpu_linear_solve': False, 'execution_profile': 'cpu-debug', 'execution_note': 'CPU debug profile disables Warp accelerated assembly paths to simplify diagnosis.'}
        compile_config, runtime_config, solver_policy = _typed_configs('cpu', compute_profile='cpu-safe', execution_profile='cpu-debug')
        return ExecutionPlan(profile='cpu-debug', device='cpu', has_cuda=has_cuda, thread_count=min(4, threads), metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    if requested == 'cpu-robust' or not has_cuda or requested_device.startswith('cpu'):
        meta = {'compute_profile': 'cpu-safe', 'control_strategy': 'commercial-safe', 'warp_nonlinear_enabled': False, 'warp_hex8_enabled': False, 'warp_interface_enabled': False, 'warp_structural_enabled': False, 'warp_full_gpu_linear_solve': False, 'execution_profile': 'cpu-robust', 'execution_note': 'CPU robust profile keeps the staged solve on conservative host-side assembly paths.'}
        compile_config, runtime_config, solver_policy = _typed_configs('cpu', compute_profile='cpu-safe', execution_profile='cpu-robust')
        return ExecutionPlan(profile='cpu-robust', device='cpu', has_cuda=has_cuda, thread_count=threads, metadata=meta, note=str(meta['execution_note']), compile_config=compile_config, runtime_config=runtime_config, solver_policy=solver_policy)
    meta = {'compute_profile': 'auto', 'control_strategy': 'commercial', 'execution_profile': 'gpu', 'execution_note': 'CUDA was detected, so the default profile keeps GPU-oriented execution paths enabled.'}
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
        }
    )
    return SolverSettings(prefer_sparse=bool(prefer_sparse), line_search=True, max_cutbacks=int(plan.solver_policy.max_cutbacks), max_iterations=12, device=plan.device, thread_count=int(plan.thread_count), metadata=metadata)
