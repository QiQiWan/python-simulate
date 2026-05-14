from __future__ import annotations

"""Qt-free controller for strengthened geometry-kernel actions."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.modules import meshing


@dataclass(slots=True)
class GeometryKernelActionController:
    project: Any | None = None

    def dependency_status(self) -> dict[str, Any]:
        return meshing.geometry_kernel_dependency_status()

    def report(self, project: Any | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.geometry_kernel_report(active)

    def optimize_stl(self, project: Any | None = None, *, tolerance: float = 1.0e-9, attach: bool = True) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.optimize_project_stl_surface(active, tolerance=tolerance, attach=attach)

    def generate_soil_layers(self, project: Any | None = None, *, layers: list[dict[str, Any]] | None = None, dims: tuple[int, int] = (1, 1), element_family: str = "hex8", attach: bool = True) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.generate_soil_layer_volume_mesh(active, layers=layers or [], dims=dims, element_family=element_family, attach=attach)

    def optimize_complex_stl(self, project: Any | None = None, *, tolerance: float = 1.0e-9, fill_holes: bool = True, orient_normals: bool = True, attach: bool = True) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.optimize_project_complex_stl_surface(active, tolerance=tolerance, fill_holes=fill_holes, orient_normals=orient_normals, attach=attach)

    def gmsh_meshio_validation(self, project: Any | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.gmsh_meshio_validation(active)

    def generate_stratigraphic_surfaces(self, project: Any | None = None, *, layers: list[dict[str, Any]] | None = None, dims: tuple[int, int] = (1, 1), element_family: str = "hex8", attach: bool = True) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.generate_stratigraphic_surface_volume_mesh(active, layers=layers or [], dims=dims, element_family=element_family, attach=attach)

    def optimize_volume_quality(self, project: Any | None = None, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 1.0e6, attach: bool = True) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.optimize_project_volume_mesh_quality(active, min_volume=min_volume, max_aspect_ratio=max_aspect_ratio, attach=attach)

    def gmsh_occ_fragment_tet4(self, project: Any | None = None, *, layers: list[dict[str, Any]] | None = None, mesh_size: float | None = None, attach: bool = True, allow_fallback: bool = True, debug: bool | None = None, debug_dir: str | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.gmsh_occ_fragment_tet4_mesh(active, layers=layers or [], mesh_size=mesh_size, attach=attach, allow_fallback=allow_fallback, debug=debug, debug_dir=debug_dir)

    def local_remesh_quality(self, project: Any | None = None, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 1.0e6, attach: bool = True, debug: bool | None = None, debug_dir: str | None = None) -> dict[str, Any]:
        active = project if project is not None else self.project
        if active is None:
            return {"ok": False, "error": "project_missing"}
        return meshing.local_remesh_project_volume_mesh_quality(active, min_volume=min_volume, max_aspect_ratio=max_aspect_ratio, attach=attach, debug=debug, debug_dir=debug_dir)

    def operation_log_status(self) -> dict[str, Any]:
        return meshing.geometry_operation_log_status()


__all__ = ["GeometryKernelActionController"]
