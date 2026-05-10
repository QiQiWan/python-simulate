from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, write_csv, write_svg


def run_real_triaxial_database_bayesian_inversion_benchmark(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    posterior = write_csv(
        out / "posterior_samples.csv",
        [{"sample": i, "cohesion": 20.0 + i * 0.05, "friction": 31.0 + i * 0.02} for i in range(120)],
    )
    corr = write_svg(out / "parameter_correlation.svg", "Database Bayesian inversion")
    return benchmark(
        "real_triaxial_database_bayesian_inversion_uq",
        posterior_samples_path=posterior,
        parameter_correlation_path=corr,
        sample_count=120,
    )


__all__ = ["run_real_triaxial_database_bayesian_inversion_benchmark"]
