from __future__ import annotations

"""Qt-free GUI controller for production geotechnical workflows."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.services import build_geotechnical_readiness_report, run_project_workflow


@dataclass(slots=True)
class GeotechnicalActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def readiness(self) -> dict[str, Any]:
        return build_geotechnical_readiness_report(self.context())

    def run_staged_mohr_coulomb(self, *, mesh_kind: str = "auto", load_increments: int = 3, max_iterations: int = 8, tolerance: float = 1.0e-5):
        return run_project_workflow(
            self.context(),
            mesh_kind=mesh_kind,
            solver_backend="staged_mohr_coulomb_cpu",
            metadata={"load_increments": load_increments, "max_iterations": max_iterations, "tolerance": tolerance},
            summarize=True,
        )


__all__ = ["GeotechnicalActionController"]
