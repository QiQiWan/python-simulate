from __future__ import annotations

"""Thin GUI main-window entrypoint.

The full Qt implementation lives in :mod:`geoai_simkit.app.main_window_impl`.
Keeping this module small prevents new GUI features from bypassing the
controller/service/module boundary and gives architecture tests a stable file to
police.
"""

from geoai_simkit.services.legacy_gui_backends import SolverSettings

from .main_window_impl import MainWindow, UIStyle, launch_main_window, resolve_app_icon

__all__ = ["MainWindow", "SolverSettings", "UIStyle", "launch_main_window", "resolve_app_icon"]


if __name__ == "__main__":  # pragma: no cover - manual GUI launcher
    launch_main_window()
