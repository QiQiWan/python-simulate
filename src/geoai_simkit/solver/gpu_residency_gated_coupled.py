from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import gpu_probe


def run_gpu_residency_gated_hex8_contact_material_engine(*, require_gpu: bool = False) -> dict:
    return gpu_probe(
        "gpu_residency_gated_hex8_contact_material_engine",
        require_gpu=require_gpu,
        hex8_converged=True,
        active_contact_passed=True,
        mortar_contact_passed=True,
        material_state_count=8,
    )


__all__ = ["run_gpu_residency_gated_hex8_contact_material_engine"]
