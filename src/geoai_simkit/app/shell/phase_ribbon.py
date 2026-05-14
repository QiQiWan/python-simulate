from __future__ import annotations

"""Headless phase ribbon model used by the Qt shell to build dynamic toolbars."""

from dataclasses import dataclass

from geoai_simkit.services.workbench_phase_service import build_workbench_phase_state, phase_workbench_ui_state


@dataclass(slots=True)
class PhaseRibbonModel:
    active_phase: str = "geology"
    active_tool: str | None = None

    def payload(self) -> dict[str, object]:
        state = build_workbench_phase_state(self.active_phase, self.active_tool)
        return state.to_dict()

    def phase_tabs(self) -> list[dict[str, object]]:
        state = build_workbench_phase_state(self.active_phase, self.active_tool)
        return [
            {"key": phase.key, "label": phase.label, "order": phase.order, "active": phase.key == state.active_phase}
            for phase in state.phases
        ]

    def toolbar_groups(self) -> dict[str, list[dict[str, object]]]:
        state = build_workbench_phase_state(self.active_phase, self.active_tool)
        return state.active_phase_spec().toolbar.tools_by_group()

    def ui_state(self) -> dict[str, object]:
        return phase_workbench_ui_state(self.active_phase, self.active_tool)

    def runtime_tool_key(self) -> str:
        return str(self.ui_state().get("runtime_tool") or "select")


__all__ = ["PhaseRibbonModel"]
