from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from geoai_simkit.pipeline.execution import build_solver_settings as build_generic_solver_settings, recommended_thread_count
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.gpu_runtime import detect_cuda_devices


DemoExecutionProfile = Literal["auto", "cpu-robust", "cpu-debug", "gpu"]


@dataclass(frozen=True, slots=True)
class DemoRuntimePlan:
    profile: str
    device: str
    has_cuda: bool
    thread_count: int
    metadata: dict[str, object]
    note: str


def recommended_demo_thread_count(*, hard_cap: int = 8) -> int:
    return recommended_thread_count(hard_cap=hard_cap)


def build_demo_runtime_plan(profile: str = "auto", *, device: str | None = None) -> DemoRuntimePlan:
    requested = str(profile or 'auto').strip().lower()
    if requested not in {'auto', 'cpu-robust', 'cpu-debug', 'gpu'}:
        requested = 'auto'
    requested_device = str(device or 'auto-best').strip().lower()
    has_cuda = bool(detect_cuda_devices())
    threads = recommended_demo_thread_count()
    if requested == 'gpu' and has_cuda and not requested_device.startswith('cpu'):
        meta: dict[str, object] = {'compute_profile': 'auto', 'control_strategy': 'commercial', 'execution_profile': 'gpu', 'execution_note': 'Using the richer GPU-capable staged solver profile.', 'demo_execution_profile': 'gpu', 'demo_execution_note': 'Using the richer GPU-capable staged solver profile.'}
        return DemoRuntimePlan(profile='gpu', device=requested_device if requested_device != 'auto' else 'auto-best', has_cuda=True, thread_count=threads, metadata=meta, note=str(meta['demo_execution_note']))
    if requested == 'cpu-debug':
        meta = {'compute_profile': 'cpu-safe', 'control_strategy': 'commercial-safe', 'warp_nonlinear_enabled': False, 'warp_hex8_enabled': False, 'warp_interface_enabled': False, 'warp_structural_enabled': False, 'warp_full_gpu_linear_solve': False, 'execution_profile': 'cpu-debug', 'execution_note': 'CPU debug profile disables Warp accelerated assembly paths to simplify diagnosis.', 'demo_execution_profile': 'cpu-debug', 'demo_execution_note': 'CPU debug profile disables Warp accelerated assembly paths to simplify diagnosis.'}
        return DemoRuntimePlan(profile='cpu-debug', device='cpu', has_cuda=has_cuda, thread_count=min(4, threads), metadata=meta, note=str(meta['demo_execution_note']))
    if requested == 'cpu-robust' or not has_cuda or requested_device.startswith('cpu'):
        meta = {'compute_profile': 'cpu-safe', 'control_strategy': 'commercial-safe', 'warp_nonlinear_enabled': False, 'warp_hex8_enabled': False, 'warp_interface_enabled': False, 'warp_structural_enabled': False, 'warp_full_gpu_linear_solve': False, 'execution_profile': 'cpu-robust', 'execution_note': 'CPU robust profile keeps the staged solve on conservative host-side assembly paths.', 'demo_execution_profile': 'cpu-robust', 'demo_execution_note': 'CPU robust profile keeps the staged solve on conservative host-side assembly paths.'}
        return DemoRuntimePlan(profile='cpu-robust', device='cpu', has_cuda=has_cuda, thread_count=threads, metadata=meta, note=str(meta['demo_execution_note']))
    meta = {'compute_profile': 'auto', 'control_strategy': 'commercial', 'execution_profile': 'gpu', 'execution_note': 'CUDA was detected, so the default demo profile keeps GPU-oriented execution paths enabled.', 'demo_execution_profile': 'gpu', 'demo_execution_note': 'CUDA was detected, so the default demo profile keeps GPU-oriented execution paths enabled.'}
    return DemoRuntimePlan(profile='gpu', device=requested_device if requested_device != 'auto' else 'auto-best', has_cuda=True, thread_count=threads, metadata=meta, note=str(meta['demo_execution_note']))


def build_demo_solver_settings(profile: str = 'auto', *, device: str | None = None, prefer_sparse: bool = True) -> SolverSettings:
    plan = build_demo_runtime_plan(profile=profile, device=device)
    settings = build_generic_solver_settings(profile=plan.profile, device=plan.device, prefer_sparse=prefer_sparse)
    settings.metadata.update(dict(plan.metadata))
    return settings
