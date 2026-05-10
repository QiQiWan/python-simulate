from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_newton_krylov_hex8_contact_material_benchmark(*, require_gpu: bool = False) -> dict:
    return gpu_probe(
        "gpu_newton_krylov_hex8_contact_material_coupled",
        require_gpu=require_gpu,
        solid_iterations=4,
        contact_iterations=2,
        material_state_count=8,
    )


__all__ = ["run_gpu_newton_krylov_hex8_contact_material_benchmark"]
