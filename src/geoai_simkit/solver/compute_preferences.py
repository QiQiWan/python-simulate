from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.solver.gpu_runtime import choose_cuda_device, detect_cuda_devices
from geoai_simkit.solver.linear_algebra import default_thread_count


@dataclass(slots=True)
class BackendComputePreferences:
    backend: str = "warp"
    profile: str = "auto"
    device: str = "auto-best"
    thread_count: int = 0
    require_warp: bool = False
    warp_hex8_enabled: bool = True
    warp_nonlinear_enabled: bool = True
    warp_full_gpu_linear_solve: bool = True
    warp_gpu_global_assembly: bool = True
    warp_interface_enabled: bool = True
    warp_structural_enabled: bool = True
    warp_unified_block_merge: bool = True
    stage_state_sync: bool = True
    ordering: str = "auto"
    preconditioner: str = "auto"
    solver_strategy: str = "auto"
    warp_preconditioner: str = "diag"
    warp_use_cuda_graph: bool = False
    multi_gpu_mode: str = "single"
    iterative_tolerance: float = 1.0e-10
    iterative_maxiter: int = 2000
    block_size: int = 3
    allowed_gpu_devices: list[str] = field(default_factory=list)
    metadata_extra: dict[str, Any] = field(default_factory=dict)

    def resolved_device(self, cuda_available: bool) -> str:
        dev = str(self.device or "auto-best").lower()
        if not cuda_available:
            return "cpu" if dev.startswith("cuda") or dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"} else dev
        if not detect_cuda_devices():
            if dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"}:
                return "cuda:0"
            if dev.startswith("cuda"):
                return dev
        if dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"}:
            return choose_cuda_device(dev, allowed_devices=self.allowed_gpu_devices)
        if dev.startswith("cuda"):
            return choose_cuda_device(dev, allowed_devices=self.allowed_gpu_devices)
        return dev

    def resolved_thread_count(self, cpu_total: int | None = None) -> int:
        if int(self.thread_count or 0) > 0:
            return int(self.thread_count)
        if cpu_total is None:
            return default_thread_count()
        return max(1, int(cpu_total) - 1)

    def to_metadata(self, *, cuda_available: bool) -> dict[str, Any]:
        requested_device = str(self.device or "auto-best").lower()
        if str(self.multi_gpu_mode or "single").lower() == "round-robin" and requested_device in {"auto", "auto-best", "best"}:
            requested_device = "auto-round-robin"
        resolved_device = self.resolved_device(cuda_available) if requested_device == str(self.device or "auto-best").lower() else (choose_cuda_device(requested_device, allowed_devices=self.allowed_gpu_devices) if cuda_available and detect_cuda_devices() else ("cuda:0" if cuda_available else "cpu"))
        meta = {
            "compute_profile": str(self.profile or "manual").lower(),
            "require_warp": bool(self.require_warp and resolved_device.startswith("cuda")),
            "warp_hex8_enabled": bool(self.warp_hex8_enabled),
            "warp_nonlinear_enabled": bool(self.warp_nonlinear_enabled),
            "warp_full_gpu_linear_solve": bool(self.warp_full_gpu_linear_solve and resolved_device.startswith("cuda")),
            "warp_gpu_global_assembly": bool(self.warp_gpu_global_assembly and resolved_device.startswith("cuda")),
            "warp_interface_enabled": bool(self.warp_interface_enabled and resolved_device.startswith("cuda")),
            "warp_structural_enabled": bool(self.warp_structural_enabled and resolved_device.startswith("cuda")),
            "warp_unified_block_merge": bool(self.warp_unified_block_merge),
            "stage_state_sync": bool(self.stage_state_sync),
            "ordering": str(self.ordering or "auto").lower(),
            "preconditioner": str(self.preconditioner or "auto").lower(),
            "solver_strategy": str(self.solver_strategy or "auto").lower(),
            "warp_preconditioner": str(self.warp_preconditioner or "diag").lower(),
            "warp_use_cuda_graph": bool(self.warp_use_cuda_graph and resolved_device.startswith("cuda")),
            "multi_gpu_mode": str(self.multi_gpu_mode or "single").lower(),
            "warp_device": requested_device if requested_device.startswith("auto-") else resolved_device,
            "warp_selected_device": resolved_device,
            "allowed_gpu_devices": [str(x) for x in self.allowed_gpu_devices if str(x).strip()],
            "warp_resident_cache": bool(resolved_device.startswith("cuda")),
            "iterative_tolerance": float(self.iterative_tolerance),
            "iterative_maxiter": int(max(25, self.iterative_maxiter)),
            "block_size": int(max(1, self.block_size)),
            "warp_check_every": int(50 if resolved_device.startswith("cuda") else 10),
            "line_search_max_iter": int(1 if resolved_device.startswith("cuda") else 3),
            "line_search_eval_limit_seconds": float(3.0 if resolved_device.startswith("cuda") else 8.0),
            "modified_newton_max_reuse": int(2 if resolved_device.startswith("cuda") else 1),
            "modified_newton_ratio_threshold": float(0.35 if resolved_device.startswith("cuda") else 0.2),
            "modified_newton_min_improvement": float(0.15),
            "adaptive_increment": True,
            "target_iterations": int(6 if resolved_device.startswith("cuda") else 5),
            "target_iteration_band_low": int(4),
            "target_iteration_band_high": int(8 if resolved_device.startswith("cuda") else 7),
            "increment_growth": float(1.35 if resolved_device.startswith("cuda") else 1.25),
            "increment_shrink": float(0.55 if resolved_device.startswith("cuda") else 0.65),
            "line_search_trigger_ratio": float(0.65),
            "line_search_correction_ratio": float(0.18),
            "displacement_tolerance_ratio": float(5.0e-3),
            "residual_plateau_window": int(3),
            "log_solver_phases": True,
            "strict_accuracy": False,
            "adaptive_small_model_cpu": bool(str(self.profile or "").lower() in {"auto", "gpu-throughput"}),
            "small_model_cpu_max_cells": int(1800),
            "small_model_cpu_max_dofs": int(18000),
        }
        if self.metadata_extra:
            meta.update(dict(self.metadata_extra))
        return meta

    def summary(self, *, cpu_total: int | None = None, cuda_available: bool = False) -> str:
        requested_device = str(self.device or "auto-best").lower()
        if str(self.multi_gpu_mode or "single").lower() == "round-robin" and requested_device in {"auto", "auto-best", "best"}:
            requested_device = "auto-round-robin"
        resolved_device = self.resolved_device(cuda_available) if requested_device == str(self.device or "auto-best").lower() else (choose_cuda_device(requested_device, allowed_devices=self.allowed_gpu_devices) if cuda_available and detect_cuda_devices() else ("cuda:0" if cuda_available else "cpu"))
        threads = self.resolved_thread_count(cpu_total)
        parts = [
            f"backend={self.backend}",
            f"device={resolved_device}",
            f"cpu_threads={threads}",
            f"ordering={self.ordering}",
            f"preconditioner={self.preconditioner}",
            "commercial_controls=on",
        ]
        if resolved_device.startswith("cuda"):
            parts.extend([
                f"require_warp={bool(self.require_warp)}",
                f"gpu_linear={bool(self.warp_full_gpu_linear_solve)}",
                f"gpu_assembly={bool(self.warp_gpu_global_assembly)}",
                f"gpu_interface={bool(self.warp_interface_enabled)}",
                f"gpu_struct={bool(self.warp_structural_enabled)}",
                f"block_merge={bool(self.warp_unified_block_merge)}",
                f"state_sync={bool(self.stage_state_sync)}",
                f"warp_nl={bool(self.warp_nonlinear_enabled)}",
                f"warp_graph={bool(self.warp_use_cuda_graph)}",
                f"multi_gpu={self.multi_gpu_mode}",
                f"gpu_pool={len([x for x in self.allowed_gpu_devices if str(x).strip()]) or "auto"}",
            ])
        else:
            parts.append("gpu_path=disabled")
        return ", ".join(parts)


def recommended_compute_preferences(profile: str, *, cuda_available: bool, cpu_total: int | None = None) -> BackendComputePreferences:
    total = max(1, int(cpu_total or default_thread_count() + 1))
    name = str(profile or "auto").lower()
    if name == "cpu-safe":
        return BackendComputePreferences(
            profile=name,
            device="cpu",
            thread_count=max(1, total // 2),
            require_warp=False,
            warp_hex8_enabled=False,
            warp_nonlinear_enabled=False,
            warp_full_gpu_linear_solve=False,
            warp_gpu_global_assembly=False,
            warp_interface_enabled=False,
            warp_structural_enabled=False,
            warp_unified_block_merge=False,
            stage_state_sync=False,
            ordering="rcm",
            preconditioner="block-jacobi",
            solver_strategy="auto",
            warp_preconditioner="diag",
            warp_use_cuda_graph=False,
            multi_gpu_mode="single",
            iterative_maxiter=1600,
        )
    if name == "gpu-fullpath":
        return BackendComputePreferences(
            profile=name,
            device="auto-best" if cuda_available else "cpu",
            thread_count=max(1, total - 1),
            require_warp=bool(cuda_available),
            warp_hex8_enabled=True,
            warp_nonlinear_enabled=True,
            warp_full_gpu_linear_solve=True,
            warp_gpu_global_assembly=True,
            warp_interface_enabled=True,
            warp_structural_enabled=True,
            warp_unified_block_merge=True,
            stage_state_sync=True,
            ordering="auto",
            preconditioner="auto",
            solver_strategy="auto",
            warp_preconditioner="diag",
            warp_use_cuda_graph=False,
            multi_gpu_mode="single",
            iterative_maxiter=2400,
        )
    if name == "gpu-throughput":
        return BackendComputePreferences(
            profile=name,
            device="auto-best" if cuda_available else "cpu",
            thread_count=max(1, total - 1),
            require_warp=bool(cuda_available),
            warp_hex8_enabled=True,
            warp_nonlinear_enabled=True,
            warp_full_gpu_linear_solve=bool(cuda_available),
            warp_gpu_global_assembly=bool(cuda_available),
            warp_interface_enabled=bool(cuda_available),
            warp_structural_enabled=bool(cuda_available),
            warp_unified_block_merge=bool(cuda_available),
            stage_state_sync=True,
            ordering="auto",
            preconditioner="auto",
            solver_strategy="auto",
            warp_preconditioner="diag",
            warp_use_cuda_graph=False,
            multi_gpu_mode="single",
            iterative_maxiter=2000,
        )
    return BackendComputePreferences(
        profile="auto",
        device="auto-best" if cuda_available else "cpu",
        thread_count=0,
        require_warp=bool(cuda_available),
        warp_hex8_enabled=bool(cuda_available),
        warp_nonlinear_enabled=bool(cuda_available),
        warp_full_gpu_linear_solve=bool(cuda_available),
        warp_gpu_global_assembly=bool(cuda_available),
        warp_interface_enabled=bool(cuda_available),
        warp_structural_enabled=bool(cuda_available),
        warp_unified_block_merge=bool(cuda_available),
        stage_state_sync=True,
        ordering="auto",
        preconditioner="auto",
        solver_strategy="auto",
        warp_preconditioner="diag",
        warp_use_cuda_graph=False,
        multi_gpu_mode="single",
        iterative_maxiter=1800,
    )
