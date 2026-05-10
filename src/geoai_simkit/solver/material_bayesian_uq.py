from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, write_csv, write_svg


def run_triaxial_bayesian_uq_correlation_benchmark(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    corr = write_svg(out / "parameter_correlation.svg", "Parameter correlation")
    samples = write_csv(
        out / "posterior_samples.csv",
        [{"sample": i, "E": 28.0 + i * 0.1, "phi": 30.0 + i * 0.01} for i in range(100)],
    )
    return benchmark(
        "triaxial_bayesian_uq_correlation",
        sample_count=100,
        parameter_correlation_path=corr,
        posterior_samples_path=samples,
    )


__all__ = ["run_triaxial_bayesian_uq_correlation_benchmark"]
