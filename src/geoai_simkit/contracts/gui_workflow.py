from __future__ import annotations

"""Phase-based GUI workflow contracts for the 3D modeling workbench."""

from dataclasses import dataclass, field
from typing import Literal, Mapping

JsonMap = Mapping[str, object]
WorkbenchPhaseKey = Literal["geology", "structures", "mesh", "staging", "solve", "results"]
ViewportInteractionMode = Literal[
    "select",
    "create_point",
    "create_line",
    "create_surface",
    "create_volume",
    "assign_semantics",
    "repair_geometry",
    "mesh_edit",
    "stage_edit",
    "result_probe",
]


@dataclass(frozen=True, slots=True)
class PhaseToolSpec:
    key: str
    label: str
    group: str
    interaction_mode: ViewportInteractionMode = "select"
    command: str = ""
    enabled: bool = True
    icon: str = ""
    tooltip: str = ""
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "group": self.group,
            "interaction_mode": self.interaction_mode,
            "command": self.command,
            "enabled": bool(self.enabled),
            "icon": self.icon,
            "tooltip": self.tooltip,
            "metadata": {"contract": "phase_tool_spec_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class PhaseToolbarSpec:
    phase_key: str
    groups: tuple[str, ...] = ()
    tools: tuple[PhaseToolSpec, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def tools_by_group(self) -> dict[str, list[dict[str, object]]]:
        grouped: dict[str, list[dict[str, object]]] = {group: [] for group in self.groups}
        for tool in self.tools:
            grouped.setdefault(tool.group, []).append(tool.to_dict())
        return grouped

    def to_dict(self) -> dict[str, object]:
        return {
            "phase_key": self.phase_key,
            "groups": list(self.groups),
            "tools": [tool.to_dict() for tool in self.tools],
            "tools_by_group": self.tools_by_group(),
            "metadata": {"contract": "phase_toolbar_spec_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class PhasePanelSpec:
    key: str
    label: str
    position: str = "left"
    component: str = ""
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "position": self.position,
            "component": self.component,
            "metadata": {"contract": "phase_panel_spec_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class PhaseCommandSpec:
    key: str
    label: str
    controller: str
    method: str
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "controller": self.controller,
            "method": self.method,
            "metadata": {"contract": "phase_command_spec_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class WorkbenchPhase:
    key: WorkbenchPhaseKey
    label: str
    order: int
    toolbar: PhaseToolbarSpec
    panels: tuple[PhasePanelSpec, ...] = ()
    default_tool: str = "select"
    allowed_selection_kinds: tuple[str, ...] = ()
    commands: tuple[PhaseCommandSpec, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "order": int(self.order),
            "toolbar": self.toolbar.to_dict(),
            "panels": [panel.to_dict() for panel in self.panels],
            "default_tool": self.default_tool,
            "allowed_selection_kinds": list(self.allowed_selection_kinds),
            "commands": [command.to_dict() for command in self.commands],
            "metadata": {"contract": "workbench_phase_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class WorkbenchPhaseState:
    active_phase: WorkbenchPhaseKey
    phases: tuple[WorkbenchPhase, ...]
    active_tool: str = "select"
    selection_filter: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def phase(self, key: str) -> WorkbenchPhase | None:
        for phase in self.phases:
            if phase.key == key:
                return phase
        return None

    def active_phase_spec(self) -> WorkbenchPhase:
        phase = self.phase(self.active_phase)
        if phase is None:
            return self.phases[0]
        return phase

    def to_dict(self) -> dict[str, object]:
        active = self.active_phase_spec()
        return {
            "active_phase": self.active_phase,
            "active_tool": self.active_tool,
            "selection_filter": list(self.selection_filter),
            "active_toolbar": active.toolbar.to_dict(),
            "active_panels": [panel.to_dict() for panel in active.panels],
            "phases": [phase.to_dict() for phase in self.phases],
            "metadata": {"contract": "workbench_phase_state_v1", **dict(self.metadata)},
        }


__all__ = [
    "JsonMap",
    "PhaseCommandSpec",
    "PhasePanelSpec",
    "PhaseToolbarSpec",
    "PhaseToolSpec",
    "ViewportInteractionMode",
    "WorkbenchPhase",
    "WorkbenchPhaseKey",
    "WorkbenchPhaseState",
]
