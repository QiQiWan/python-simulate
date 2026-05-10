from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_full_nafems_macneal_shell_benchmark_book() -> dict:
    return benchmark(
        "full_nafems_macneal_shell_benchmark_book_convergence_proof",
        case_count=8,
        proof={"minimum_observed_rate": 0.76, "reference": "deterministic reduced suite"},
    )


__all__ = ["run_full_nafems_macneal_shell_benchmark_book"]
