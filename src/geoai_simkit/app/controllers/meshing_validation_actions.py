from __future__ import annotations

"""Qt-free controller for production meshing validation diagnostics."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.modules import meshing


@dataclass(slots=True)
class MeshingValidationActionController:
    project: Any | None = None

    def dependency_status(self) -> dict[str, Any]:
        return meshing.optional_mesher_dependency_status()

    def stl_repair_report(self, project: Any | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.analyze_stl_repair_readiness(active)

    def production_report(self, project: Any | None = None, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.production_meshing_validation(active, solver_backend=solver_backend)

    def region_rows(self, project: Any | None = None) -> list[dict[str, Any]]:
        active = project if project is not None else self.project
        if active is None:
            return []
        return meshing.region_mesh_quality_summary(active)


__all__ = ["MeshingValidationActionController"]
