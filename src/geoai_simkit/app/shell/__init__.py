from __future__ import annotations

from .phase_workbench_qt import launch_phase_workbench_qt


def launch_unified_workbench() -> None:
    """Compatibility alias for the canonical workbench."""

    launch_phase_workbench_qt()


__all__ = ["launch_phase_workbench_qt", "launch_unified_workbench"]
