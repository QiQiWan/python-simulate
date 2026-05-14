from __future__ import annotations

"""Removed historical Qt main-window implementation.

GeoAI SimKit 1.6.4 has one GUI state machine and one supported desktop
window: :mod:`geoai_simkit.app.shell.phase_workbench_qt`.  This module remains
only so old imports fail with an explicit message instead of launching stale UI
logic.
"""

from typing import Any

REMOVED_LEGACY_GUI_IMPL = True
CANONICAL_WORKBENCH = "geoai_simkit.app.shell.phase_workbench_qt"


class MainWindow:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Legacy main_window_impl is removed. Use repository-root start_gui.py / PhaseWorkbenchQt.")


def launch_main_window_impl() -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["CANONICAL_WORKBENCH", "REMOVED_LEGACY_GUI_IMPL", "MainWindow", "launch_main_window_impl"]
