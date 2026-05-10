from __future__ import annotations


def test_hex8_sparse_nonlinear_benchmark_contract():
    from geoai_simkit.solver.sparse_nonlinear import run_hex8_sparse_nonlinear_benchmark
    out = run_hex8_sparse_nonlinear_benchmark()
    assert out["sparse_assembly"] is True
    assert out["n_elements"] >= 12
    assert out["passed"] is True


def test_mindlin_plate_shell_bending_contract():
    from geoai_simkit.solver.structural.global_coupling import run_mindlin_plate_shell_bending_benchmark
    out = run_mindlin_plate_shell_bending_benchmark()
    assert out["formulation"].startswith("Mindlin")
    assert out["plate_tip_w"] < 0.0
    assert out["shell_tip_w"] < 0.0
    assert out["passed"] is True


def test_augmented_lagrangian_mortar_contact_contract():
    from geoai_simkit.solver.interface_element import run_interface_augmented_lagrangian_mortar_benchmark
    out = run_interface_augmented_lagrangian_mortar_benchmark()
    assert out["contact_seen"] is True
    assert out["bounded_friction"] is True
    assert out["passed"] is True


def test_material_reference_curve_report(tmp_path):
    from geoai_simkit.solver.material_path_report import run_mc_hss_global_convergence_reference_benchmark
    out = run_mc_hss_global_convergence_reference_benchmark(tmp_path)
    assert out["passed"] is True
    assert (tmp_path / "mc_pq_reference.svg").exists()
    assert (tmp_path / "hss_reduction_reference.svg").exists()


def test_gpu_native_benchmark_records_capability():
    from geoai_simkit.solver.gpu_native import run_gpu_native_nonlinear_assembly_benchmark
    out = run_gpu_native_nonlinear_assembly_benchmark(require_gpu=False)
    assert "gpu_native_ran" in out
    assert "capability" in out
    assert out["passed"] is True


def test_iter86_full_suite_contains_new_benchmarks(tmp_path):
    from geoai_simkit.solver.nonlinear_benchmarks import run_nonlinear_global_benchmark_suite
    out = run_nonlinear_global_benchmark_suite(tmp_path)
    names = {b["name"] for b in out["benchmarks"]}
    assert "hex8_sparse_nonlinear_global_solve" in names
    assert "mindlin_plate_shell_bending" in names
    assert "interface_augmented_lagrangian_mortar_contact" in names
    assert "mc_hss_reference_curve_convergence_report" in names
    assert "gpu_native_nonlinear_assembly" in names
