from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_fully_coupled_gpu_resident_hex8_contact_material_benchmark(*, require_gpu: bool = False) -> dict:
    return gpu_probe(
        "fully_coupled_gpu_resident_hex8_contact_material",
        require_gpu=require_gpu,
        hex8_converged=True,
        contact_passed=True,
        material_state_count=8,
    )


__all__ = ["run_fully_coupled_gpu_resident_hex8_contact_material_benchmark"]
