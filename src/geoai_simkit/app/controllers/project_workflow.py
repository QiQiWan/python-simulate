from __future__ import annotations

"""Headless project workflow controller used by GUI actions."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.modules.fem_solver import solve_project
from geoai_simkit.modules.meshing import generate_project_mesh
from geoai_simkit.modules.postprocessing import summarize_results
from geoai_simkit.modules.stage_planning import compile_project_stages


@dataclass(slots=True)
class ProjectWorkflowController:
    """Orchestrates the standard mesh -> stage -> solve -> post workflow."""

    project: Any

    def context(self):
        return as_project_context(self.project)

    def generate_mesh(self, *, mesh_kind: str = "auto", attach: bool = True, **options: Any):
        return generate_project_mesh(self.context(), mesh_kind=mesh_kind, attach=attach, options=options)

    def compile_stages(self, *stage_ids: str):
        return compile_project_stages(self.context(), stage_ids=stage_ids)

    def solve(self, *, backend_preference: str = "reference_cpu", write_results: bool = True):
        return solve_project(self.context(), backend_preference=backend_preference, write_results=write_results)

    def summarize_results(self, *, processor: str = "auto"):
        return summarize_results(self.context(), processor=processor)


__all__ = ["ProjectWorkflowController"]
