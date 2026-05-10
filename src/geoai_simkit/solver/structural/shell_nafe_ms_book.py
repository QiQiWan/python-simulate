from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_shell_benchmark_book() -> dict:
    return benchmark(
        "shell_benchmark_book",
        bending_error_convergence=[0.22, 0.13, 0.07, 0.035],
        distortion_sensitivity=[0.11, 0.10, 0.09, 0.08],
    )


__all__ = ["run_shell_benchmark_book"]
