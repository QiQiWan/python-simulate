from __future__ import annotations

from pathlib import Path


def test_preconditioner_chain_contract():
    from geoai_simkit.solver.linsys.preconditioned import benchmark_preconditioner_chain
    out = benchmark_preconditioner_chain()
    assert out["passed"] is True
    assert out["backend"]
    assert out["preconditioner"]


def test_gpu_kernelized_benchmark_has_truthful_status():
    from geoai_simkit.solver.gpu_native import run_gpu_native_nonlinear_assembly_benchmark
    out = run_gpu_native_nonlinear_assembly_benchmark(require_gpu=False)
    assert out["name"] == "gpu_native_kernelized_hex8_nonlinear_assembly"
    assert "gpu_native_ran" in out
    if out["gpu_native_ran"]:
        assert out["status"] == "gpu-kernel-ran"
        assert out["kernel_result"]["ran"] is True
    else:
        assert out["status"] == "capability_missing"


def test_industrial_shell_bending_locking_benchmark():
    from geoai_simkit.solver.structural.global_coupling import run_industrial_shell_bending_locking_benchmark
    out = run_industrial_shell_bending_locking_benchmark()
    assert out["passed"] is True
    assert out["formulation"].startswith("MITC4")
    assert len(out["tip_values"]) == 3


def test_complex_mortar_face_search_benchmark():
    from geoai_simkit.solver.contact.mortar import run_complex_wall_soil_mortar_search_benchmark
    out = run_complex_wall_soil_mortar_search_benchmark()
    assert out["passed"] is True
    assert out["pair_count"] == 2
    assert all(r["active_gauss_points"] > 0 for r in out["pair_reports"])


def test_mc_hss_triaxial_calibration_report(tmp_path: Path):
    from geoai_simkit.solver.material_calibration import run_mc_hss_triaxial_calibration_benchmark
    out = run_mc_hss_triaxial_calibration_benchmark(tmp_path)
    assert out["passed"] is True
    report = out["report"]
    assert report["mohr_coulomb"]["metrics"]["r2"] > 0.80
    assert report["hss_small"]["metrics"]["r2"] > 0.90
    assert (tmp_path / "triaxial_calibration_fit.svg").exists()


def test_nonlinear_suite_contains_industrial_core_entries(tmp_path: Path):
    from geoai_simkit.solver.nonlinear_benchmarks import run_nonlinear_global_benchmark_suite
    out = run_nonlinear_global_benchmark_suite(tmp_path)
    names = {b["name"] for b in out["benchmarks"]}
    assert "amg_ilu_krylov_preconditioner_chain" in names
    assert "industrial_mitc4_shell_bending_locking_local_corotational" in names
    assert "complex_wall_soil_mortar_search_and_face_integration" in names
    assert "mc_hss_triaxial_curve_calibration_and_error" in names
    assert "gpu_native_kernelized_hex8_nonlinear_assembly" in names
