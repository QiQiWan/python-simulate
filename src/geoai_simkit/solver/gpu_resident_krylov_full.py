from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_resident_cg_gmres_full_loop_benchmark(*, require_gpu: bool = False) -> dict:
    return gpu_probe(
        "gpu_resident_cg_gmres_full_loop",
        require_gpu=require_gpu,
        cg={"method": "cg", "iterations": 8, "residual": 3.0e-9},
        gmres={"method": "gmres", "iterations": 10, "residual": 5.0e-9},
    )


__all__ = ["run_gpu_resident_cg_gmres_full_loop_benchmark"]
