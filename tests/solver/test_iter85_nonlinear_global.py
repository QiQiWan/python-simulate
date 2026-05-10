from __future__ import annotations

from pathlib import Path


def test_hex8_nonlinear_global_solve_benchmark():
    from geoai_simkit.solver.hex8_global import run_hex8_nonlinear_global_solve_benchmark

    result = run_hex8_nonlinear_global_solve_benchmark()
    assert result["passed"] is True
    assert result["iterations"] > 0


def test_interface_active_set_loop():
    from geoai_simkit.solver.interface_element import run_interface_active_set_nonlinear_benchmark

    result = run_interface_active_set_nonlinear_benchmark()
    assert result["passed"] is True
    assert result["iterations"] >= 1


def test_shell_bending_benchmark():
    from geoai_simkit.solver.structural.global_coupling import run_shell_bending_benchmark

    result = run_shell_bending_benchmark()
    assert result["passed"] is True
    assert result["tip_w"] < 0.0


def test_material_path_report_exports(tmp_path: Path):
    from geoai_simkit.solver.material_path_report import export_material_path_report

    summary = export_material_path_report(tmp_path)
    assert summary["accepted"] is True
    assert Path(summary["mohr_coulomb"]["svg"]).exists()
    assert Path(summary["hss_small"]["svg"]).exists()


def test_hss_hssmall_global_nonlinear_benchmark():
    from geoai_simkit.solver.nonlinear_benchmarks import run_hss_hssmall_global_nonlinear_benchmark

    result = run_hss_hssmall_global_nonlinear_benchmark()
    assert result["passed"] is True
    assert result["consistent_tangent_ok"] is True


def test_nonlinear_global_suite_and_benchmark_report(tmp_path: Path):
    from geoai_simkit.solver.benchmark_report import write_benchmark_report

    summary = write_benchmark_report(tmp_path)
    assert summary["accepted"] is True
    assert Path(summary["json_path"]).exists()
    assert Path(summary["markdown_path"]).exists()
    assert Path(summary["gui_payload_path"]).exists()
