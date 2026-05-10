from __future__ import annotations

"""Qt-free quality-gate controller for verified 3D geotechnical workflows."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.modules.geotechnical import quality_gate


@dataclass(slots=True)
class QualityGateActionController:
    project: Any | None = None

    def report(self, project: Any | None = None, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return quality_gate(active, solver_backend=solver_backend)


__all__ = ["QualityGateActionController"]
