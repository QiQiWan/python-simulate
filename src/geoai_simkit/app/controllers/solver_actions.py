from __future__ import annotations

"""GUI-facing solve action controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import project_compiled_phase_summary
from geoai_simkit.modules import fem_solver


@dataclass(slots=True)
class SolverActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def phase_summary(self) -> dict[str, Any]:
        return project_compiled_phase_summary(self.context()).to_dict()

    def supported_backends(self) -> list[str]:
        return fem_solver.solver_backend_registry().keys()

    def capabilities(self) -> list[dict[str, object]]:
        return fem_solver.solver_backend_capabilities()

    def solve(self, *, backend_preference: str = "reference_cpu", write_results: bool = True):
        return fem_solver.solve_project(self.context(), backend_preference=backend_preference, write_results=write_results)


__all__ = ["SolverActionController"]
