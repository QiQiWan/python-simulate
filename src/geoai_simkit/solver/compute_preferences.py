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
    selected_gpu_aliases: tuple[str, ...] = ()
    metadata_extra: dict[str, Any] = field(default_factory=dict)

    def resolved_device(self, cuda_available: bool) -> str:
        dev = str(self.device or "auto-best").lower()
        allowed = [str(v).lower() for v in self.selected_gpu_aliases if str(v).strip()]
        if not cuda_available:
            return "cpu" if dev.startswith("cuda") or dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"} else dev
        if not detect_cuda_devices():
            if dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"}:
                return "cuda:0"
            if dev.startswith("cuda"):
                return dev
        if dev in {"auto", "auto-best", "best", "cuda", "auto-round-robin", "round-robin", "auto-rr"}:
            return choose_cuda_device(dev, allowed_aliases=allowed)
        if dev.startswith("cuda"):
            return choose_cuda_device(dev, allowed_aliases=allowed)
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
        allowed = [str(v).lower() for v in self.selected_gpu_aliases if str(v).strip()]
        resolved_device = self.resolved_device(cuda_available) if requested_device == str(self.device or "auto-best").lower() else (choose_cuda_device(requested_device, allowed_aliases=allowed) if cuda_available and detect_cuda_devices() else ("cuda:0" if cuda_available else "cpu"))
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
            "iterative_tolerance": float(self.iterative_tolerance),
            "iterative_maxiter": int(max(25, self.iterative_maxiter)),
            "block_size": int(max(1, self.block_size)),
            "allowed_gpu_devices": [str(v) for v in self.selected_gpu_aliases if str(v).strip()],
        }
        if self.metadata_extra:
            meta.update(dict(self.metadata_extra))
        return meta

    def summary(self, *, cpu_total: int | None = None, cuda_available: bool = False) -> str:
        requested_device = str(self.device or "auto-best").lower()
        if str(self.multi_gpu_mode or "single").lower() == "round-robin" and requested_device in {"auto", "auto-best", "best"}:
            requested_device = "auto-round-robin"
        allowed = [str(v).lower() for v in self.selected_gpu_aliases if str(v).strip()]
        resolved_device = self.resolved_device(cuda_available) if requested_device == str(self.device or "auto-best").lower() else (choose_cuda_device(requested_device, allowed_aliases=allowed) if cuda_available and detect_cuda_devices() else ("cuda:0" if cuda_available else "cpu"))
        threads = self.resolved_thread_count(cpu_total)
        parts = [
            f"backend={self.backend}",
            f"device={resolved_device}",
            f"cpu_threads={threads}",
            f"ordering={self.ordering}",
            f"preconditioner={self.preconditioner}",
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
                f"selected_gpus={len(self.selected_gpu_aliases) if self.selected_gpu_aliases else 'all'}",
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
            metadata_extra={
                "line_search_mode": "always",
                "line_search_eval_limit_seconds": 8.0,
                "line_search_small_step_ratio": 1.0e-5,
                "warmup_gpu": False,
            },
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
            metadata_extra={
                "line_search_mode": "adaptive",
                "line_search_eval_limit_seconds": 3.0,
                "line_search_small_step_ratio": 2.0e-4,
                "line_search_accept_ratio": 0.85,
                "warmup_gpu": True,
            },
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
            metadata_extra={
                "line_search_mode": "adaptive",
                "line_search_eval_limit_seconds": 2.5,
                "line_search_small_step_ratio": 2.0e-4,
                "line_search_accept_ratio": 0.85,
                "warmup_gpu": True,
            },
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
        metadata_extra={
            "line_search_mode": "adaptive" if cuda_available else "always",
            "line_search_eval_limit_seconds": 3.0 if cuda_available else 8.0,
            "line_search_small_step_ratio": 2.0e-4 if cuda_available else 1.0e-5,
            "line_search_accept_ratio": 0.85 if cuda_available else 0.70,
            "warmup_gpu": bool(cuda_available),
        },
    )
