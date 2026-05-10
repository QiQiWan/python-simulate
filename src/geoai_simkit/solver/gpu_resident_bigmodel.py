from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_resident_large_model_benchmark(*, require_gpu: bool = False) -> dict:
    return gpu_probe("gpu_resident_global_csr_large_model", require_gpu=require_gpu, n_dof=144, nnz=1728)


__all__ = ["run_gpu_resident_large_model_benchmark"]
