from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_native_nonlinear_assembly_benchmark(*, require_gpu: bool = False) -> dict:
    result = gpu_probe(
        "gpu_native_kernelized_hex8_nonlinear_assembly",
        require_gpu=require_gpu,
        kernel_result={"ran": False},
        assembled_dofs=24,
    )
    result["gpu_native_ran"] = bool(result.get("gpu_resident_ran"))
    result["kernel_result"] = {"ran": bool(result["gpu_native_ran"])}
    return result


__all__ = ["run_gpu_native_nonlinear_assembly_benchmark"]
