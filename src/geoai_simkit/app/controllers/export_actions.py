from __future__ import annotations

"""Qt-free export action controller."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.services.legacy_gui_backends import ExportManager


@dataclass(slots=True)
class ExportActionController:
    manager: ExportManager = field(default_factory=ExportManager)

    def export_status(self) -> dict[str, Any]:
        return {"available": True, "manager": type(self.manager).__name__, "contract": "export_action_controller_v1"}

    def export(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.manager.export(*args, **kwargs)


__all__ = ["ExportActionController"]
