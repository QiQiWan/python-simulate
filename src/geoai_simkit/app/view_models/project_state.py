from __future__ import annotations

"""Dependency-light project state view models for GUI presenters."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.adapters import as_project_context


@dataclass(frozen=True, slots=True)
class ProjectStateViewModel:
    project_id: str
    name: str
    geometry_count: int
    mesh_cell_count: int
    stage_count: int
    result_stage_count: int
    plugin_status: dict[str, Any] = field(default_factory=dict)


def view_model_from_project(project: Any, *, plugin_status: dict[str, Any] | None = None) -> ProjectStateViewModel:
    snapshot = as_project_context(project).snapshot()
    return ProjectStateViewModel(
        project_id=snapshot.project_id,
        name=snapshot.name,
        geometry_count=snapshot.geometry_count,
        mesh_cell_count=snapshot.mesh_cell_count,
        stage_count=snapshot.stage_count,
        result_stage_count=snapshot.result_stage_count,
        plugin_status=dict(plugin_status or {}),
    )


__all__ = ["ProjectStateViewModel", "view_model_from_project"]
