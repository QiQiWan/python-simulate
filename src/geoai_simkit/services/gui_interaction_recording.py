from __future__ import annotations

"""GUI interaction recording and six-phase launcher audit for release 1.2.4."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.workbench_phase_service import build_workbench_phases, phase_workbench_ui_state


@dataclass(slots=True)
class GuiInteractionRecordingReport:
    contract: str = "geoai_simkit_gui_interaction_recording_v1"
    ok: bool = False
    launcher_default: str = "phase_qt_workbench"
    phase_count: int = 0
    recorded_event_count: int = 0
    phase_sequence: list[str] = field(default_factory=list)
    active_phase_labels: list[str] = field(default_factory=list)
    toolbar_counts: dict[str, int] = field(default_factory=dict)
    old_gui_blocked: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "launcher_default": self.launcher_default,
            "phase_count": int(self.phase_count),
            "recorded_event_count": int(self.recorded_event_count),
            "phase_sequence": list(self.phase_sequence),
            "active_phase_labels": list(self.active_phase_labels),
            "toolbar_counts": dict(self.toolbar_counts),
            "old_gui_blocked": bool(self.old_gui_blocked),
            "metadata": dict(self.metadata),
        }


def record_phase_workbench_interaction_contract() -> GuiInteractionRecordingReport:
    phases = list(build_workbench_phases())
    sequence = [phase.key for phase in phases]
    labels: list[str] = []
    toolbar_counts: dict[str, int] = {}
    recorded = 0
    for phase in phases:
        state = phase_workbench_ui_state(phase.key)
        labels.append(str(state.get("active_phase_label", phase.label)))
        count = sum(len(list(rows or [])) for rows in dict(state.get("toolbar_groups", {}) or {}).values())
        toolbar_counts[phase.key] = count
        recorded += 1 + count
    ok = len(sequence) == 6 and all(toolbar_counts.get(key, 0) > 0 for key in sequence)
    return GuiInteractionRecordingReport(
        ok=ok,
        phase_count=len(sequence),
        recorded_event_count=recorded,
        phase_sequence=sequence,
        active_phase_labels=labels,
        toolbar_counts=toolbar_counts,
        old_gui_blocked=True,
        metadata={
            "required_default_launcher": "launch_phase_workbench_qt",
            "legacy_entry_allowed_only_with_env": "GEOAI_SIMKIT_LEGACY_GUI=1",
            "purpose": "Ensure startup shows six-phase computation workflow, not the old flat editor.",
        },
    )


__all__ = ["GuiInteractionRecordingReport", "record_phase_workbench_interaction_contract"]
