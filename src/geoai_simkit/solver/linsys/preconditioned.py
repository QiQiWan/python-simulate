from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def benchmark_preconditioner_chain() -> dict:
    return benchmark(
        "amg_ilu_krylov_preconditioner_chain",
        backend="scipy-csr-reference",
        preconditioner="jacobi+ilu-contract",
        iterations=9,
    )


__all__ = ["benchmark_preconditioner_chain"]
