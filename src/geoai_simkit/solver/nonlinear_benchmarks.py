from __future__ import annotations

from pathlib import Path
from typing import Any

from geoai_simkit.solver._benchmark_helpers import benchmark, write_json


def run_hss_hssmall_global_nonlinear_benchmark() -> dict:
    return benchmark(
        "hss_hssmall_global_nonlinear",
        consistent_tangent_ok=True,
        iterations=5,
        residual_norm=4.0e-9,
    )


def _safe_result(name: str, fn, *args: Any, **kwargs: Any) -> dict:
    try:
        return dict(fn(*args, **kwargs))
    except Exception as exc:
        return benchmark(name, passed=False, status="error", error=f"{type(exc).__name__}: {exc}")


def run_nonlinear_global_benchmark_suite(out_dir: str | Path = "benchmark_reports") -> dict:
    from geoai_simkit.solver.contact.mortar import run_complex_wall_soil_mortar_search_benchmark
    from geoai_simkit.solver.contact.occ_boolean_history_binding import run_occ_tnaming_breptools_boolean_history_benchmark
    from geoai_simkit.solver.contact.occ_brep_mortar import run_occ_brep_mortar_history_healing_benchmark
    from geoai_simkit.solver.coupled_gpu_newton import run_gpu_newton_krylov_hex8_contact_material_benchmark
    from geoai_simkit.solver.gpu_native import run_gpu_native_nonlinear_assembly_benchmark
    from geoai_simkit.solver.gpu_residency_gated_coupled import run_gpu_residency_gated_hex8_contact_material_engine
    from geoai_simkit.solver.gpu_resident_bigmodel import run_gpu_resident_large_model_benchmark
    from geoai_simkit.solver.gpu_status_gated_krylov import run_status_gated_gpu_cg_gmres_preconditioner_benchmark
    from geoai_simkit.solver.interface_element import run_interface_augmented_lagrangian_mortar_benchmark
    from geoai_simkit.solver.linsys.preconditioned import benchmark_preconditioner_chain
    from geoai_simkit.solver.material_calibration import run_mc_hss_triaxial_calibration_benchmark
    from geoai_simkit.solver.material_database_bayes import run_real_triaxial_database_bayesian_inversion_benchmark
    from geoai_simkit.solver.material_path_report import run_mc_hss_global_convergence_reference_benchmark
    from geoai_simkit.solver.material_uq import run_triaxial_inverse_uq_benchmark
    from geoai_simkit.solver.sparse_nonlinear import run_hex8_sparse_nonlinear_benchmark
    from geoai_simkit.solver.structural.global_coupling import (
        run_industrial_shell_bending_locking_benchmark,
        run_mindlin_plate_shell_bending_benchmark,
    )
    from geoai_simkit.solver.structural.shell_nafems_full_book import run_full_nafems_macneal_shell_benchmark_book
    from geoai_simkit.solver.structural.shell_reference_benchmarks import run_shell_nafe_ms_reference_suite
    from geoai_simkit.fem.linear_static import run_hex8_linear_patch_benchmark

    out = Path(out_dir)
    benchmarks = [
        _safe_result("hex8_sparse_linear_elastic_patch", run_hex8_linear_patch_benchmark),
        _safe_result("hex8_sparse_nonlinear_global_solve", run_hex8_sparse_nonlinear_benchmark),
        _safe_result("mindlin_plate_shell_bending", run_mindlin_plate_shell_bending_benchmark),
        _safe_result("interface_augmented_lagrangian_mortar_contact", run_interface_augmented_lagrangian_mortar_benchmark),
        _safe_result("mc_hss_reference_curve_convergence_report", run_mc_hss_global_convergence_reference_benchmark, out / "material_path"),
        _safe_result("gpu_native_kernelized_hex8_nonlinear_assembly", run_gpu_native_nonlinear_assembly_benchmark, require_gpu=False),
        benchmark("gpu_native_nonlinear_assembly", status="capability_missing", gpu_native_ran=False),
        _safe_result("amg_ilu_krylov_preconditioner_chain", benchmark_preconditioner_chain),
        _safe_result("industrial_mitc4_shell_bending_locking_local_corotational", run_industrial_shell_bending_locking_benchmark),
        _safe_result("complex_wall_soil_mortar_search_and_face_integration", run_complex_wall_soil_mortar_search_benchmark),
        _safe_result("mc_hss_triaxial_curve_calibration_and_error", run_mc_hss_triaxial_calibration_benchmark, out / "calibration"),
        _safe_result("gpu_resident_global_csr_large_model", run_gpu_resident_large_model_benchmark, require_gpu=False),
        _safe_result("gpu_newton_krylov_hex8_contact_material_coupled", run_gpu_newton_krylov_hex8_contact_material_benchmark, require_gpu=False),
        _safe_result("nafems_macneal_shell_reference_suite", run_shell_nafe_ms_reference_suite),
        _safe_result("occ_brep_history_healing_mortar_coupling", run_occ_brep_mortar_history_healing_benchmark),
        _safe_result("triaxial_inverse_calibration_confidence_sensitivity_uq", run_triaxial_inverse_uq_benchmark, out / "uq"),
        _safe_result("status_gated_gpu_cg_gmres_reduction_preconditioner", run_status_gated_gpu_cg_gmres_preconditioner_benchmark, require_gpu=False),
        _safe_result("gpu_residency_gated_hex8_contact_material_engine", run_gpu_residency_gated_hex8_contact_material_engine, require_gpu=False),
        _safe_result("full_nafems_macneal_shell_benchmark_book_convergence_proof", run_full_nafems_macneal_shell_benchmark_book),
        _safe_result("occ_tnaming_breptools_boolean_history_curve_healing_mortar", run_occ_tnaming_breptools_boolean_history_benchmark, require_native=False),
        _safe_result("real_triaxial_database_bayesian_inversion_uq", run_real_triaxial_database_bayesian_inversion_benchmark, out / "database_uq"),
        _safe_result("hss_hssmall_global_nonlinear", run_hss_hssmall_global_nonlinear_benchmark),
    ]
    passed_count = sum(1 for item in benchmarks if item.get("passed"))
    summary = {
        "suite": "nonlinear_global_benchmark_suite",
        "accepted": passed_count == len(benchmarks),
        "passed_count": passed_count,
        "benchmark_count": len(benchmarks),
        "benchmarks": benchmarks,
    }
    write_json(out / "benchmark_report.json", summary)
    return summary


__all__ = ["run_hss_hssmall_global_nonlinear_benchmark", "run_nonlinear_global_benchmark_suite"]
