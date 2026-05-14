from pathlib import Path


def test_phase_qt_background_tasks_use_threadpool_and_main_thread_timer() -> None:
    text = Path('src/geoai_simkit/app/shell/phase_workbench_qt.py').read_text(encoding='utf-8')
    assert 'ThreadPoolExecutor(max_workers=1' in text
    assert 'QtCore.QTimer(self)' in text
    assert 'worker.moveToThread' not in text
    assert 'thread.wait' not in text
    assert 'QGraphicsView' not in text
    assert 'QtInteractor' in text
    assert '3D PyVista/VTK 模型视口已刷新' in text


def test_nextgen_background_tasks_use_threadpool_and_no_qthread_wait() -> None:
    text = Path('src/geoai_simkit/app/workbench_window.py').read_text(encoding='utf-8')
    assert 'ThreadPoolExecutor(max_workers=1' in text
    assert 'QtCore.QTimer(self)' in text
    assert 'thread.wait' not in text
    assert 'worker.moveToThread' not in text


def test_pyside_workbench_no_longer_contains_2d_preview_copy() -> None:
    text = Path('src/geoai_simkit/app/shell/phase_workbench_qt.py').read_text(encoding='utf-8')
    forbidden_phrases = [
        '上方为 Qt 轻量模型预览',
        '二维剖面预览',
        'phase-workbench-2d-model-view',
    ]
    for phrase in forbidden_phrases:
        assert phrase not in text
