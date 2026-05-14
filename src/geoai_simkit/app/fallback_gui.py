from __future__ import annotations

"""Deprecated Tk fallback facade.

The application no longer falls back to a separate Tk GUI.  Use
``python start_gui.py --qt-only`` for the same PhaseWorkbenchQt workflow without
PyVista/VTK rendering.
"""


def build_fallback_payload() -> dict[str, object]:
    return {
        "contract": "geoai_simkit_fallback_gui_disabled_v1",
        "message": "Tk fallback is disabled. Use start_gui.py --qt-only.",
        "canonical_workbench": "geoai_simkit.app.shell.phase_workbench_qt",
    }


def launch_tk_fallback_workbench(error_message: str = "") -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["build_fallback_payload", "launch_tk_fallback_workbench"]
