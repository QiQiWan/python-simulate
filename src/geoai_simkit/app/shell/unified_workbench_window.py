from __future__ import annotations

"""Compatibility payload facade for legacy callers.

The historical unified launcher no longer selects between multiple GUI windows.
All launch requests go to PhaseWorkbenchQt.  Payload helpers remain lightweight
for tests and non-GUI tools that need a summary.
"""

from typing import Any


def build_unified_workbench_payload(document: Any | None = None) -> dict[str, Any]:
    try:
        from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload

        payload = build_phase_workbench_qt_payload()
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "contract": "unified_workbench_payload_v3_redirected",
        "canonical_workbench": "geoai_simkit.app.shell.phase_workbench_qt",
        "legacy_launcher_disabled": True,
        "phase_workbench_payload": payload,
    }


class UnifiedWorkbenchController:
    def __init__(self, document: Any | None = None) -> None:
        self.document = document

    def refresh_payload(self) -> dict[str, Any]:
        return build_unified_workbench_payload(self.document)

    @property
    def payload(self) -> dict[str, Any]:
        return self.refresh_payload()


def launch_unified_workbench() -> None:
    from geoai_simkit.app.shell.phase_workbench_qt import launch_phase_workbench_qt

    launch_phase_workbench_qt()


__all__ = ["UnifiedWorkbenchController", "build_unified_workbench_payload", "launch_unified_workbench"]
