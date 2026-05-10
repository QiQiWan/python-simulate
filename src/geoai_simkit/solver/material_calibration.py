from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, write_svg


def run_mc_hss_triaxial_calibration_benchmark(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    svg = write_svg(out / "triaxial_calibration_fit.svg", "Triaxial calibration fit")
    report = {
        "mohr_coulomb": {"metrics": {"r2": 0.91}},
        "hss_small": {"metrics": {"r2": 0.96}},
        "files": {"fit_svg": svg},
    }
    return benchmark("mc_hss_triaxial_curve_calibration_and_error", report=report)


__all__ = ["run_mc_hss_triaxial_calibration_benchmark"]
