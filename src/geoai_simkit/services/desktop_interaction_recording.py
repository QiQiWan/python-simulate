from __future__ import annotations

"""Headless contract for desktop interaction recording regression tests.

Real GUI recording can be performed with Qt test/OS tooling on a desktop, but
this service provides the stable event script and expected observations used by
CI and by the startup diagnostics panel.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DesktopInteractionRecordingContract:
    contract: str = "desktop_interaction_recording_contract_v1"
    recorder: str = "qtbot_or_qt_test_desktop_recorder"
    required_sequences: list[dict[str, Any]] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "recorder": self.recorder,
            "required_sequences": [dict(row) for row in self.required_sequences],
            "expected_artifacts": list(self.expected_artifacts),
            "ok": bool(self.ok),
        }


def build_desktop_interaction_recording_contract() -> DesktopInteractionRecordingContract:
    sequences = [
        {"name": "load_template", "steps": ["open_startup_preflight", "enter_phase_workbench", "load_foundation_pit_3d_beta"], "assert": "3d_viewport_has_primitives"},
        {"name": "create_geometry", "steps": ["activate_point", "click_viewport", "activate_line", "click_two_points", "undo", "redo"], "assert": "command_stack_mutates_document"},
        {"name": "edit_handles", "steps": ["select_volume", "show_edit_handles", "activate_move", "drag_handle"], "assert": "volume_bounds_changed"},
        {"name": "numeric_edit", "steps": ["select_entity", "edit_xyz_or_dimensions", "apply"], "assert": "entity_coordinates_changed"},
        {"name": "semantic_assignment", "steps": ["select_surface", "choose_wall", "choose_concrete", "apply"], "assert": "structure_or_material_mapping_created"},
        {"name": "complete_calculation", "steps": ["run_current_template", "wait_finished", "export_bundle"], "assert": "vtk_and_report_exist"},
    ]
    return DesktopInteractionRecordingContract(required_sequences=sequences, expected_artifacts=["interaction_recording.json", "viewport_before.png", "viewport_after.png", "demo_review_bundle"])


__all__ = ["DesktopInteractionRecordingContract", "build_desktop_interaction_recording_contract"]
