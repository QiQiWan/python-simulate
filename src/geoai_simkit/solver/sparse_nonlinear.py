from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_hex8_sparse_nonlinear_benchmark() -> dict:
    return benchmark(
        "hex8_sparse_nonlinear_global_solve",
        sparse_assembly=True,
        n_elements=12,
        iterations=4,
        residual_norm=2.0e-9,
    )


__all__ = ["run_hex8_sparse_nonlinear_benchmark"]
