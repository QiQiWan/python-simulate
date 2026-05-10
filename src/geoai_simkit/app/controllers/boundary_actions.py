from __future__ import annotations

"""Qt-free GUI boundary/load summary controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts.geotechnical import boundary_condition_summary, load_summary


@dataclass(slots=True)
class BoundaryConditionActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def boundary_summary(self) -> dict[str, Any]:
        return boundary_condition_summary(self.context()).to_dict()

    def load_summary(self) -> dict[str, Any]:
        return load_summary(self.context()).to_dict()

    def summary(self) -> dict[str, Any]:
        return {"boundary_conditions": self.boundary_summary(), "loads": self.load_summary()}


__all__ = ["BoundaryConditionActionController"]
