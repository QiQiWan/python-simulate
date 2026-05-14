from __future__ import annotations

"""Qt-free controller for phase-based workbench navigation."""

from geoai_simkit.services.workbench_phase_service import build_workbench_phase_state, build_workbench_phases, phase_toolbar_rows, phase_workbench_ui_state


class WorkbenchPhaseActionController:
    def phases(self) -> list[dict[str, object]]:
        return [phase.to_dict() for phase in build_workbench_phases()]

    def state(self, active_phase: str = "geology", active_tool: str | None = None) -> dict[str, object]:
        return build_workbench_phase_state(active_phase, active_tool).to_dict()

    def toolbar_rows(self, active_phase: str = "geology") -> list[dict[str, object]]:
        return phase_toolbar_rows(active_phase)

    def ui_state(self, active_phase: str = "geology", active_tool: str | None = None) -> dict[str, object]:
        return phase_workbench_ui_state(active_phase, active_tool)


__all__ = ["WorkbenchPhaseActionController"]
