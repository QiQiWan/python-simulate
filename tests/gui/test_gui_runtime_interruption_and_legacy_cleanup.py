from pathlib import Path


def test_unified_launcher_no_longer_imports_legacy_flat_windows():
    text = Path('src/geoai_simkit/app/shell/unified_workbench_window.py').read_text(encoding='utf-8')
    assert 'launch_modern_qt_workbench' not in text
    assert 'launch_main_window' not in text
    assert 'launch_tk_fallback_workbench' not in text
    assert 'Legacy flat GUI launch is disabled' in text


def test_phase_qt_demo_actions_use_background_worker():
    text = Path('src/geoai_simkit/app/shell/phase_workbench_qt.py').read_text(encoding='utf-8')
    assert 'class _BackgroundWorker' in text
    assert '_start_background_operation' in text
    assert 'run_demo_complete_calculation(demo_id' in text
    assert 'run_all_demo_calculations(output_dir=target)' in text
    assert 'Operation already running' in text


def test_nextgen_solver_run_uses_background_worker():
    text = Path('src/geoai_simkit/app/workbench_window.py').read_text(encoding='utf-8')
    assert 'class _BackgroundWorker' in text
    assert '_start_background_operation' in text
    assert "NextGen solver run" in text
