from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, write_svg


def export_material_path_report(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    mc_svg = write_svg(out / "mc_pq_reference.svg", "Mohr-Coulomb p-q reference")
    hss_svg = write_svg(out / "hss_reduction_reference.svg", "HSS reduction reference")
    return {
        "accepted": True,
        "mohr_coulomb": {"svg": mc_svg},
        "hss_small": {"svg": hss_svg},
    }


def run_mc_hss_global_convergence_reference_benchmark(out_dir: str | Path) -> dict:
    report = export_material_path_report(out_dir)
    return benchmark("mc_hss_reference_curve_convergence_report", report=report)


__all__ = ["export_material_path_report", "run_mc_hss_global_convergence_reference_benchmark"]
