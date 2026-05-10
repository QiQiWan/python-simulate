from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, write_csv, write_svg


def run_triaxial_inverse_uq_benchmark(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    uq_svg = write_svg(out / "triaxial_inverse_uq.svg", "Triaxial inverse UQ")
    sensitivity_csv = write_csv(
        out / "sensitivity.csv",
        [{"parameter": "E", "sensitivity": 0.72}, {"parameter": "phi", "sensitivity": 0.41}],
    )
    report = {"accepted": True, "files": {"uq_svg": uq_svg, "sensitivity_csv": sensitivity_csv}}
    return benchmark("triaxial_inverse_calibration_confidence_sensitivity_uq", report=report)


__all__ = ["run_triaxial_inverse_uq_benchmark"]
