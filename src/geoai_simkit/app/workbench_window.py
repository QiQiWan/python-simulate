from __future__ import annotations

"""Deprecated GUI entrypoint redirected to the canonical PhaseWorkbenchQt.

The historical next-generation workbench implementation is intentionally removed from the launchable code path in 1.6.4. It did not include the import-driven assembly action dispatcher and could make the repaired GUI appear unchanged.
"""


def launch_nextgen_workbench() -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["launch_nextgen_workbench"]
