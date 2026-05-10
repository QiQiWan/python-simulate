from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver.gpu_status_gated_krylov import run_status_gated_gpu_cg_gmres_preconditioner_benchmark
from geoai_simkit.solver.gpu_residency_gated_coupled import run_gpu_residency_gated_hex8_contact_material_engine
from geoai_simkit.solver.structural.shell_nafems_full_book import run_full_nafems_macneal_shell_benchmark_book
from geoai_simkit.solver.contact.occ_boolean_history_binding import run_occ_tnaming_breptools_boolean_history_benchmark
from geoai_simkit.solver.material_database_bayes import run_real_triaxial_database_bayesian_inversion_benchmark
from geoai_simkit.solver.nonlinear_benchmarks import run_nonlinear_global_benchmark_suite


def test_status_gated_gpu_krylov_truthful_optional_path():
    out = run_status_gated_gpu_cg_gmres_preconditioner_benchmark(require_gpu=False)
    assert out["passed"] is True
    assert "cg" in out and "gmres" in out
    assert out["cpu_reference_used"] in {True, False}


def test_gpu_residency_gated_coupled_hex8_contact_material_gate():
    out = run_gpu_residency_gated_hex8_contact_material_engine(require_gpu=False)
    assert out["passed"] is True
    assert out["hex8_converged"] is True
    assert out["active_contact_passed"] is True
    assert out["mortar_contact_passed"] is True


def test_full_shell_benchmark_book_has_convergence_proof():
    out = run_full_nafems_macneal_shell_benchmark_book()
    assert out["passed"] is True
    assert out["case_count"] >= 8
    assert out["proof"]["minimum_observed_rate"] > 0.5


def test_occ_tnaming_boolean_history_binding_truthful_fallback():
    out = run_occ_tnaming_breptools_boolean_history_benchmark(require_native=False)
    assert out["passed"] is True
    assert out["history_event_count"] >= 2
    assert out["backend"]


def test_triaxial_database_bayesian_inversion_outputs(tmp_path: Path):
    out = run_real_triaxial_database_bayesian_inversion_benchmark(tmp_path / "uq")
    assert out["passed"] is True
    assert Path(out["posterior_samples_path"]).exists()
    assert Path(out["parameter_correlation_path"]).exists()


def test_full_suite_contains_iter92_entries(tmp_path: Path):
    summary = run_nonlinear_global_benchmark_suite(tmp_path / "reports")
    names = {item.get("name") for item in summary["benchmarks"]}
    assert "status_gated_gpu_cg_gmres_reduction_preconditioner" in names
    assert "gpu_residency_gated_hex8_contact_material_engine" in names
    assert "full_nafems_macneal_shell_benchmark_book_convergence_proof" in names
    assert "occ_tnaming_breptools_boolean_history_curve_healing_mortar" in names
    assert "real_triaxial_database_bayesian_inversion_uq" in names
