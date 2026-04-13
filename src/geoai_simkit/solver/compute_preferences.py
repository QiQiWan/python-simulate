from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.solver.linear_algebra import default_thread_count


@dataclass(slots=True)
class BackendComputePreferences:
    backend: str = "warp"
    profile: str = "auto"
    device: str = "auto"
    thread_count: int = 0
    require_warp: bool = False
    warp_hex8_enabled: bool = True
    warp_nonlinear_enabled: bool = True
    warp_full_gpu_linear_solve: bool = True
    warp_gpu_global_assembly: bool = True
    warp_interface_enabled: bool = True
    warp_structural_enabled: bool = True
    warp_unified_block_merge: bool = True
    ordering: str = "auto"
    preconditioner: str = "auto"
    solver_strategy: str = "auto"
    warp_preconditioner: str = "diag"
    iterative_tolerance: float = 1.0e-10
    iterative_maxiter: int = 2000
    block_size: int = 3
    metadata_extra: dict[str, Any] = field(default_factory=dict)

    def resolved_device(self, cuda_available: bool) -> str:
        dev = str(self.device or "auto").lower()
        if dev == "auto":
            return "cuda" if cuda_available else "cpu"
        if dev.startswith("cuda") and not cuda_available:
            return "cpu"
        return dev

    def resolved_thread_count(self, cpu_total: int | None = None) -> int:
        if int(self.thread_count or 0) > 0:
            return int(self.thread_count)
        if cpu_total is None:
            return default_thread_count()
        return max(1, int(cpu_total) - 1)

    def to_metadata(self, *, cuda_available: bool) -> dict[str, Any]:
        resolved_device = self.resolved_device(cuda_available)
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
            "ordering": str(self.ordering or "auto").lower(),
            "preconditioner": str(self.preconditioner or "auto").lower(),
            "solver_strategy": str(self.solver_strategy or "auto").lower(),
            "warp_preconditioner": str(self.warp_preconditioner or "diag").lower(),
            "iterative_tolerance": float(self.iterative_tolerance),
            "iterative_maxiter": int(max(25, self.iterative_maxiter)),
            "block_size": int(max(1, self.block_size)),
        }
        if self.metadata_extra:
            meta.update(dict(self.metadata_extra))
        return meta

    def summary(self, *, cpu_total: int | None = None, cuda_available: bool = False) -> str:
        resolved_device = self.resolved_device(cuda_available)
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
                f"warp_nl={bool(self.warp_nonlinear_enabled)}",
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
            ordering="rcm",
            preconditioner="block-jacobi",
            solver_strategy="auto",
            warp_preconditioner="diag",
            iterative_maxiter=1600,
        )
    if name == "gpu-fullpath":
        return BackendComputePreferences(
            profile=name,
            device="cuda" if cuda_available else "cpu",
            thread_count=max(1, total - 1),
            require_warp=bool(cuda_available),
            warp_hex8_enabled=True,
            warp_nonlinear_enabled=True,
            warp_full_gpu_linear_solve=True,
            warp_gpu_global_assembly=True,
            warp_interface_enabled=True,
            warp_structural_enabled=True,
            warp_unified_block_merge=True,
            ordering="auto",
            preconditioner="auto",
            solver_strategy="auto",
            warp_preconditioner="diag",
            iterative_maxiter=2400,
        )
    if name == "gpu-throughput":
        return BackendComputePreferences(
            profile=name,
            device="cuda" if cuda_available else "cpu",
            thread_count=max(1, total - 1),
            require_warp=bool(cuda_available),
            warp_hex8_enabled=True,
            warp_nonlinear_enabled=True,
            warp_full_gpu_linear_solve=bool(cuda_available),
            warp_gpu_global_assembly=bool(cuda_available),
            warp_interface_enabled=bool(cuda_available),
            warp_structural_enabled=bool(cuda_available),
            warp_unified_block_merge=bool(cuda_available),
            ordering="auto",
            preconditioner="auto",
            solver_strategy="auto",
            warp_preconditioner="diag",
            iterative_maxiter=2000,
        )
    return BackendComputePreferences(
        profile="auto",
        device="cuda" if cuda_available else "cpu",
        thread_count=0,
        require_warp=bool(cuda_available),
        warp_hex8_enabled=bool(cuda_available),
        warp_nonlinear_enabled=bool(cuda_available),
        warp_full_gpu_linear_solve=bool(cuda_available),
        warp_gpu_global_assembly=bool(cuda_available),
        warp_interface_enabled=bool(cuda_available),
        warp_structural_enabled=bool(cuda_available),
        warp_unified_block_merge=bool(cuda_available),
        ordering="auto",
        preconditioner="auto",
        solver_strategy="auto",
        warp_preconditioner="diag",
        iterative_maxiter=1800,
    )
