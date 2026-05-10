from __future__ import annotations

"""Data-lineage flags for interactive FEM modeling."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DirtyState:
    geometry_dirty: bool = False
    topology_dirty: bool = False
    mesh_dirty: bool = False
    material_dirty: bool = False
    stage_dirty: bool = False
    solve_dirty: bool = False
    result_stale: bool = False
    messages: list[str] = field(default_factory=list)

    def mark_geometry_changed(self, message: str = "geometry changed") -> None:
        self.geometry_dirty = True
        self.topology_dirty = True
        self.mesh_dirty = True
        self.solve_dirty = True
        self.result_stale = True
        self.messages.append(message)

    def mark_stage_changed(self, message: str = "stage plan changed") -> None:
        self.stage_dirty = True
        self.solve_dirty = True
        self.result_stale = True
        self.messages.append(message)

    def mark_mesh_generated(self) -> None:
        self.mesh_dirty = False
        self.solve_dirty = True
        self.result_stale = True
        self.messages.append("mesh regenerated")

    def mark_solved(self) -> None:
        self.solve_dirty = False
        self.result_stale = False
        self.messages.append("solution updated")

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_dirty": self.geometry_dirty,
            "topology_dirty": self.topology_dirty,
            "mesh_dirty": self.mesh_dirty,
            "material_dirty": self.material_dirty,
            "stage_dirty": self.stage_dirty,
            "solve_dirty": self.solve_dirty,
            "result_stale": self.result_stale,
            "messages": list(self.messages[-20:]),
        }
