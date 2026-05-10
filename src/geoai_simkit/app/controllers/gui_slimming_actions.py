from __future__ import annotations

"""Qt-free controller for GUI modularization/slimming status."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services import build_gui_slimming_report


@dataclass(slots=True)
class GuiSlimmingActionController:
    """Expose GUI slimming metrics for status panels without importing Qt."""

    max_main_window_lines: int = 5900
    metadata: dict[str, Any] | None = None

    def report(self) -> dict[str, Any]:
        payload = build_gui_slimming_report(max_main_window_lines=self.max_main_window_lines).to_dict()
        if self.metadata:
            payload.setdefault("metadata", {}).update(self.metadata)
        return payload

    def main_window_metric(self) -> dict[str, Any]:
        metrics = self.report().get("metrics", [])
        return dict(metrics[0]) if metrics else {}


__all__ = ["GuiSlimmingActionController"]
