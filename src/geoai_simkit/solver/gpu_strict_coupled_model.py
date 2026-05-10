from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_strict_gpu_resident_engineering_model_benchmark(*, require_gpu: bool = False) -> dict:
    result = gpu_probe(
        "strict_gpu_resident_engineering_model",
        require_gpu=require_gpu,
        resident_components_required=["assembly", "krylov", "contact", "material"],
        subreports={"assembly": "reference", "contact": "reference", "material": "reference"},
    )
    result["status_gate"] = "gpu-strict" if result.get("gpu_resident_ran") else "reference-only-not-accepted-gpu"
    return result


__all__ = ["run_strict_gpu_resident_engineering_model_benchmark"]
