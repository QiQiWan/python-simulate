from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_krylov_kernel_completeness_benchmark(*, require_gpu: bool = False) -> dict:
    result = gpu_probe(
        "gpu_krylov_kernel_completeness",
        require_gpu=require_gpu,
        coverage={"spmv": True, "dot": True, "axpy": True, "preconditioner": True},
    )
    result["gpu_kernel_complete"] = bool(result.get("gpu_resident_ran"))
    return result


__all__ = ["run_gpu_krylov_kernel_completeness_benchmark"]
