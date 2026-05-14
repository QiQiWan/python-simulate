from __future__ import annotations

"""Deprecated PySide-only sketch workbench redirected to PhaseWorkbenchQt."""


def launch_modern_qt_workbench() -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["launch_modern_qt_workbench"]
