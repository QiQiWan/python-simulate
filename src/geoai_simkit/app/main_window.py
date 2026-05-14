from __future__ import annotations

"""Deprecated main-window facade.

1.6.4 makes PhaseWorkbenchQt the only supported GUI window.  This compatibility
module keeps older imports from crashing, but all launch requests are redirected
instead of instantiating the historical MainWindow implementation.
"""

from geoai_simkit.services.legacy_gui_backends import SolverSettings


class UIStyle:  # compatibility shell for import-based callers
    pass


class MainWindow:  # compatibility shell for import-based callers
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Legacy MainWindow is disabled. Use start_gui.py / PhaseWorkbenchQt.")


def resolve_app_icon(*args, **kwargs):
    return None


def launch_main_window() -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["MainWindow", "SolverSettings", "UIStyle", "launch_main_window", "resolve_app_icon"]


if __name__ == "__main__":  # pragma: no cover
    launch_main_window()
