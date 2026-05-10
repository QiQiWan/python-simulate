from __future__ import annotations

from geoai_simkit.solver.gpu_krylov_kernel_complete import run_gpu_krylov_kernel_completeness_benchmark
from geoai_simkit.solver.gpu_strict_coupled_model import run_strict_gpu_resident_engineering_model_benchmark
from geoai_simkit.solver.structural.shell_benchmark_book_traceability import run_shell_nafems_original_reference_comparison
from geoai_simkit.solver.contact.occ_boolean_end_to_end import run_occ_boolean_tnaming_end_to_end_verification


def test_gpu_krylov_kernel_completeness_truthful():
    r = run_gpu_krylov_kernel_completeness_benchmark(require_gpu=False)
    assert r["passed"] is True
    assert "gpu_kernel_complete" in r
    assert "coverage" in r
    if not r["gpu_kernel_complete"]:
        assert r["status"] == "capability_missing"
        assert r["cpu_reference_used"] is True


def test_strict_gpu_resident_coupled_engineering_model_truthful():
    r = run_strict_gpu_resident_engineering_model_benchmark(require_gpu=False)
    assert r["passed"] is True
    assert r["status_gate"] in {"gpu-strict", "reference-only-not-accepted-gpu"}
    assert "subreports" in r
    assert "resident_components_required" in r


def test_shell_reference_traceability_report(tmp_path):
    r = run_shell_nafems_original_reference_comparison(out_dir=tmp_path)
    assert r["status"] in {"official_reference_missing", "official-reference-compared"}
    assert (tmp_path / "shell_reference_traceability.json").exists()


def test_occ_boolean_end_to_end_truthful(tmp_path):
    r = run_occ_boolean_tnaming_end_to_end_verification(require_native=False, out_dir=tmp_path)
    assert r["passed"] is True
    assert r["status"] in {"native_occ_end_to_end", "fallback_ledger_only"}
    assert (tmp_path / "occ_boolean_tnaming_end_to_end.json").exists()
