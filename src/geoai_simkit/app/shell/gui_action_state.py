from __future__ import annotations

"""Qt-independent GUI action state contract.

This module records the production interaction model used by PhaseWorkbenchQt.
It is deliberately independent from PySide so startup and CI can verify that the
GUI has one action system and no residual legacy window routing.
"""

from dataclasses import asdict, dataclass
from typing import Callable, Any

GUI_ACTION_STATE_CONTRACT = "geoai_simkit_gui_action_state_v1"


@dataclass(slots=True)
class GuiActionDescriptor:
    action_id: str
    label: str
    panel: str
    expected_effect: str
    dialog_policy: str = "none"
    connected: bool = True
    status: str = "not clicked"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GuiActionStateRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, GuiActionDescriptor] = {}
        self._status: dict[str, str] = {}

    def register(self, descriptor: GuiActionDescriptor) -> GuiActionDescriptor:
        self._actions[descriptor.action_id] = descriptor
        self._status.setdefault(descriptor.action_id, descriptor.status)
        return descriptor

    def set_status(self, action_id: str, status: str) -> None:
        self._status[str(action_id)] = str(status)
        if action_id in self._actions:
            self._actions[action_id].status = str(status)

    def rows(self) -> list[dict[str, Any]]:
        return [row.to_dict() | {"status": self._status.get(row.action_id, row.status)} for row in self._actions.values()]

    def to_dict(self) -> dict[str, Any]:
        return {"contract": GUI_ACTION_STATE_CONTRACT, "action_count": len(self._actions), "actions": self.rows()}


__all__ = ["GUI_ACTION_STATE_CONTRACT", "GuiActionDescriptor", "GuiActionStateRegistry"]
