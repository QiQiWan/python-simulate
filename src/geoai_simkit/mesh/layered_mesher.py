from __future__ import annotations

"""Structured volume mesher for interpolated borehole layer surfaces."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geology.layer_surfaces import interpolate_project_layer_surfaces
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap


@dataclass(slots=True)
class LayeredMeshResult:
    mesh: MeshDocument
    layer_count: int
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.mesh.cell_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "layer_count": int(self.layer_count),
            "node_count": self.mesh.node_count,
            "cell_count": self.mesh.cell_count,
            "warnings": list(self.warnings),
        }


def _grid_from_surface(surface: Any) -> dict[str, Any] | None:
    grid = dict(getattr(surface, "metadata", {}).get("surface_grid", {}) or {})
    if not grid:
        return None
    points = [tuple(float(v) for v in point) for point in list(grid.get("points", []) or [])]
    cells = [tuple(int(v) for v in cell) for cell in list(grid.get("cells", []) or [])]
    shape_values = list(grid.get("shape", []) or [])
    if len(shape_values) != 2 or not points or not cells:
        return None
    return {"points": points, "cells": cells, "shape": (int(shape_values[0]), int(shape_values[1]))}


def _layer_id_from_volume(volume: Any) -> str:
    layer_id = getattr(volume, "metadata", {}).get("layer_id") if getattr(volume, "metadata", None) else None
    if layer_id:
        return str(layer_id)
    volume_id = str(getattr(volume, "id", ""))
    return volume_id.removeprefix("volume_")


def _cell_volume(nodes: list[tuple[float, float, float]], cell: tuple[int, ...]) -> float:
    pts = [nodes[idx] for idx in cell]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return max(max(xs) - min(xs), 0.0) * max(max(ys) - min(ys), 0.0) * max(max(zs) - min(zs), 0.0)


def generate_layered_volume_mesh(
    project: Any,
    *,
    nx: int = 5,
    ny: int = 5,
    interpolate_missing: bool = True,
    attach: bool = True,
) -> LayeredMeshResult:
    if interpolate_missing:
        interpolate_project_layer_surfaces(project, nx=nx, ny=ny, update=True)

    nodes: list[tuple[float, float, float]] = []
    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    block_tags: list[str] = []
    layer_tags: list[str] = []
    material_tags: list[str] = []
    role_tags: list[str] = []
    block_to_cells: dict[str, list[int]] = {}
    face_to_faces: dict[str, list[int]] = {}
    warnings: list[str] = []

    volumes = getattr(getattr(project, "geometry_model", None), "volumes", {})
    surfaces = getattr(getattr(project, "soil_model", None), "soil_layer_surfaces", {})
    for volume_id, volume in volumes.items():
        source = dict(getattr(volume, "metadata", {}) or {})
        if source.get("source") != "borehole_csv":
            continue
        layer_id = _layer_id_from_volume(volume)
        top_surface_id = f"layer_{layer_id}_top"
        bottom_surface_id = f"layer_{layer_id}_bottom"
        top_surface = surfaces.get(top_surface_id)
        bottom_surface = surfaces.get(bottom_surface_id)
        if top_surface is None or bottom_surface is None:
            warnings.append(f"Volume {volume_id} is missing top/bottom interpolated layer surfaces.")
            continue
        top_grid = _grid_from_surface(top_surface)
        bottom_grid = _grid_from_surface(bottom_surface)
        if top_grid is None or bottom_grid is None:
            warnings.append(f"Volume {volume_id} has layer surfaces without usable surface_grid metadata.")
            continue
        if top_grid["shape"] != bottom_grid["shape"] or len(top_grid["points"]) != len(bottom_grid["points"]):
            warnings.append(f"Volume {volume_id} top and bottom surface grids do not match.")
            continue
        base_top = len(nodes)
        nodes.extend(top_grid["points"])
        base_bottom = len(nodes)
        nodes.extend(bottom_grid["points"])
        for quad in top_grid["cells"]:
            top = tuple(base_top + idx for idx in quad)
            bottom = tuple(base_bottom + idx for idx in quad)
            # Hex8 order follows bottom face first, then top face.
            cell = (bottom[0], bottom[1], bottom[2], bottom[3], top[0], top[1], top[2], top[3])
            if _cell_volume(nodes, cell) <= 1.0e-12:
                continue
            cell_id = len(cells)
            cells.append(cell)
            cell_types.append("hex8")
            block_tags.append(str(volume_id))
            layer_tags.append(layer_id)
            material_tags.append(str(getattr(volume, "material_id", "") or ""))
            role_tags.append(str(getattr(volume, "role", "soil") or "soil"))
            block_to_cells.setdefault(str(volume_id), []).append(cell_id)
        face_to_faces.setdefault(top_surface_id, []).extend(block_to_cells.get(str(volume_id), []))
        face_to_faces.setdefault(bottom_surface_id, []).extend(block_to_cells.get(str(volume_id), []))

    if not cells:
        warnings.append("No layered volume cells were generated from interpolated layer surfaces.")
    mesh = MeshDocument(
        nodes=nodes,
        cells=cells,
        cell_types=cell_types,
        cell_tags={
            "block_id": block_tags,
            "layer_id": layer_tags,
            "material_id": material_tags,
            "role": role_tags,
        },
        entity_map=MeshEntityMap(block_to_cells=block_to_cells, face_to_faces=face_to_faces, metadata={"source": "layered_surface_mesher"}),
        quality=MeshQualityReport(
            min_quality=1.0 if cells else 0.0,
            max_aspect_ratio=None,
            bad_cell_ids=[],
            warnings=["structured layered mesh from borehole surface grids", *warnings],
        ),
        metadata={
            "mesher": "layered_surface_mesher",
            "source": "SoilLayerSurface.surface_grid",
            "grid_shape": [max(int(ny), 2), max(int(nx), 2)],
            "requires_volume_meshing": False,
        },
    )
    if attach:
        project.mesh_model.attach_mesh(mesh)
        project.mesh_model.mesh_settings.element_family = "hex8"
        project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] = False
        project.mesh_model.metadata["last_mesher"] = "layered_surface_mesher"
    return LayeredMeshResult(mesh=mesh, layer_count=len(block_to_cells), warnings=warnings)


__all__ = ["LayeredMeshResult", "generate_layered_volume_mesh"]
