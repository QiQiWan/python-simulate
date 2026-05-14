from __future__ import annotations

"""Qt-free controller for complete 3D mesh diagnostics."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.modules import meshing


@dataclass(slots=True)
class Complete3DMeshActionController:
    project: Any | None = None

    def supported_generators(self) -> list[str]:
        return meshing.supported_3d_mesh_generators()

    def tag_boundary_faces(self, project: Any | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.tag_project_3d_boundary_faces(active)

    def boundary_face_rows(self, project: Any | None = None) -> list[dict[str, Any]]:
        active = project if project is not None else self.project
        if active is None:
            return []
        return meshing.project_3d_boundary_faces(active)

    def complete_report(self, project: Any | None = None, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.complete_3d_mesh_report(active, solver_backend=solver_backend)


__all__ = ["Complete3DMeshActionController"]
