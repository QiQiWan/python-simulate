from __future__ import annotations

"""Headless phase sidebar model for tree/panel selection by workbench phase."""

from dataclasses import dataclass

from geoai_simkit.services.workbench_phase_service import build_workbench_phase_state


@dataclass(slots=True)
class PhaseSidebarModel:
    active_phase: str = "geology"

    def panels(self) -> list[dict[str, object]]:
        state = build_workbench_phase_state(self.active_phase)
        return [panel.to_dict() for panel in state.active_phase_spec().panels]

    def selection_filter(self) -> list[str]:
        state = build_workbench_phase_state(self.active_phase)
        return list(state.selection_filter)


__all__ = ["PhaseSidebarModel"]
