from __future__ import annotations

from pathlib import Path


def test_gpu_resident_cg_gmres_full_loop_truthful():
    from geoai_simkit.solver.gpu_resident_krylov_full import run_gpu_resident_cg_gmres_full_loop_benchmark
    result = run_gpu_resident_cg_gmres_full_loop_benchmark(require_gpu=False)
    assert result['passed'] is True
    assert 'gpu_resident_ran' in result
    assert 'cpu_reference_used' in result
    assert result['cg']['method'] == 'cg'
    assert result['gmres']['method'] == 'gmres'


def test_fully_coupled_gpu_hex8_contact_material_gate():
    from geoai_simkit.solver.gpu_fully_coupled import run_fully_coupled_gpu_resident_hex8_contact_material_benchmark
    result = run_fully_coupled_gpu_resident_hex8_contact_material_benchmark(require_gpu=False)
    assert result['passed'] is True
    assert result['hex8_converged'] is True
    assert result['contact_passed'] is True
    assert result['material_state_count'] >= 1


def test_shell_benchmark_book():
    from geoai_simkit.solver.structural.shell_nafe_ms_book import run_shell_benchmark_book
    result = run_shell_benchmark_book()
    assert result['passed'] is True
    assert len(result['bending_error_convergence']) >= 4
    assert len(result['distortion_sensitivity']) >= 4


def test_occ_native_history_healing_mortar():
    from geoai_simkit.solver.contact.occ_native_history import run_occ_native_history_healing_mortar_benchmark
    result = run_occ_native_history_healing_mortar_benchmark()
    assert result['passed'] is True
    assert result['healed_face_count'] >= 12
    assert result['history_contract']['shape_history']


def test_bayesian_uq_correlation_report(tmp_path: Path):
    from geoai_simkit.solver.material_bayesian_uq import run_triaxial_bayesian_uq_correlation_benchmark
    result = run_triaxial_bayesian_uq_correlation_benchmark(tmp_path)
    assert result['passed'] is True
    assert result['sample_count'] >= 100
    assert (tmp_path / 'parameter_correlation.svg').exists()
    assert (tmp_path / 'posterior_samples.csv').exists()


def test_gui_fallback_payload_imports_without_desktop_stack():
    from geoai_simkit.app.fallback_gui import build_fallback_payload
    payload = build_fallback_payload()
    assert payload['title'].startswith('GeoAI SimKit')
    assert 'workspace' in payload
