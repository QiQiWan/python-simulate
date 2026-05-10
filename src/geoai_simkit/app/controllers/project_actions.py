from __future__ import annotations

"""GUI-facing project state controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import (
    project_geometry_summary,
    project_material_summary,
    project_mesh_summary,
    project_port_capabilities,
    project_result_store_summary,
    project_stage_summary,
)


@dataclass(slots=True)
class ProjectActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def snapshot(self) -> dict[str, Any]:
        return self.context().snapshot().to_dict()

    def resource_summary(self) -> dict[str, Any]:
        context = self.context()
        return {
            "snapshot": context.snapshot().to_dict(),
            "capabilities": project_port_capabilities(context).to_dict(),
            "geometry": project_geometry_summary(context).to_dict(),
            "mesh": project_mesh_summary(context).to_dict(),
            "stages": project_stage_summary(context).to_dict(),
            "materials": project_material_summary(context).to_dict(),
            "results": project_result_store_summary(context).to_dict(),
        }


__all__ = ["ProjectActionController"]
