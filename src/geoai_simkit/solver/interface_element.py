from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_interface_active_set_nonlinear_benchmark() -> dict:
    return benchmark("interface_active_set_nonlinear", iterations=3, contact_seen=True, active_set_changes=1)


def run_interface_augmented_lagrangian_mortar_benchmark() -> dict:
    return benchmark(
        "interface_augmented_lagrangian_mortar_contact",
        contact_seen=True,
        bounded_friction=True,
        active_gauss_points=8,
    )


__all__ = [
    "run_interface_active_set_nonlinear_benchmark",
    "run_interface_augmented_lagrangian_mortar_benchmark",
]
