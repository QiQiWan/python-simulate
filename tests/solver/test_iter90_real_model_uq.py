from __future__ import annotations

from pathlib import Path


def test_gpu_resident_large_model_benchmark_optional() -> None:
    from geoai_simkit.solver.gpu_resident_bigmodel import run_gpu_resident_large_model_benchmark

    result = run_gpu_resident_large_model_benchmark(require_gpu=False)
    assert result["name"] == "gpu_resident_global_csr_large_model"
    assert result["passed"] is True
    assert result["n_dof"] > 0
    assert result["nnz"] > 0


def test_coupled_gpu_newton_krylov_benchmark_optional() -> None:
    from geoai_simkit.solver.coupled_gpu_newton import run_gpu_newton_krylov_hex8_contact_material_benchmark

    result = run_gpu_newton_krylov_hex8_contact_material_benchmark(require_gpu=False)
    assert result["name"] == "gpu_newton_krylov_hex8_contact_material_coupled"
    assert result["passed"] is True
    assert result["solid_iterations"] > 0


def test_shell_reference_suite() -> None:
    from geoai_simkit.solver.structural.shell_reference_benchmarks import run_shell_nafe_ms_reference_suite

    result = run_shell_nafe_ms_reference_suite()
    assert result["passed"] is True
    assert result["case_count"] >= 6
    assert result["max_relative_error"] < 0.20


def test_occ_brep_mortar_healing_benchmark() -> None:
    from geoai_simkit.solver.contact.occ_brep_mortar import run_occ_brep_mortar_history_healing_benchmark

    result = run_occ_brep_mortar_history_healing_benchmark()
    assert result["passed"] is True
    assert result["pair_count"] > 0
    assert result["healing"]["output_faces"] > 0


def test_triaxial_inverse_uq_report(tmp_path: Path) -> None:
    from geoai_simkit.solver.material_uq import run_triaxial_inverse_uq_benchmark

    result = run_triaxial_inverse_uq_benchmark(tmp_path)
    assert result["passed"] is True
    report = result["report"]
    assert report["accepted"] is True
    assert Path(report["files"]["uq_svg"]).exists()
    assert Path(report["files"]["sensitivity_csv"]).exists()


def test_full_suite_contains_real_model_uq_entries(tmp_path: Path) -> None:
    from geoai_simkit.solver.nonlinear_benchmarks import run_nonlinear_global_benchmark_suite

    summary = run_nonlinear_global_benchmark_suite(tmp_path)
    names = {b["name"] for b in summary["benchmarks"]}
    assert "gpu_resident_global_csr_large_model" in names
    assert "gpu_newton_krylov_hex8_contact_material_coupled" in names
    assert "nafems_macneal_shell_reference_suite" in names
    assert "occ_brep_history_healing_mortar_coupling" in names
    assert "triaxial_inverse_calibration_confidence_sensitivity_uq" in names
