import os
import pytest


def test_main_window_has_gpu_selection_helpers():
    pytest.importorskip('PySide6')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from geoai_simkit.app.main_window import MainWindow

    assert hasattr(MainWindow, '_populate_gpu_device_list')
    assert hasattr(MainWindow, '_selected_gpu_devices')


def test_main_window_has_standard_icon_helper():
    pytest.importorskip('PySide6')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from geoai_simkit.app.main_window import MainWindow

    assert hasattr(MainWindow, '_apply_standard_icons')
