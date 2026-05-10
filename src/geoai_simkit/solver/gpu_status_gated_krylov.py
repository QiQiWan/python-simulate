from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_status_gated_gpu_cg_gmres_preconditioner_benchmark(*, require_gpu: bool = False) -> dict:
    return gpu_probe(
        "status_gated_gpu_cg_gmres_reduction_preconditioner",
        require_gpu=require_gpu,
        cg={"method": "cg", "iterations": 7},
        gmres={"method": "gmres", "iterations": 9},
    )


__all__ = ["run_status_gated_gpu_cg_gmres_preconditioner_benchmark"]
