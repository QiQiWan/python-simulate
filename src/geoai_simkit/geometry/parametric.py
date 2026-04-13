from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyvista as pv

from geoai_simkit.geometry.scene_graph import SceneNode


@dataclass(slots=True)
class ParametricPitScene:
    length: float = 60.0
    width: float = 30.0
    depth: float = 20.0
    soil_depth: float = 40.0
    nx: int = 16
    ny: int = 10
    nz: int = 12
    wall_thickness: float = 0.8

    def _make_structured_soil(self) -> pv.UnstructuredGrid:
        x = np.linspace(-self.length, self.length, self.nx)
        y = np.linspace(-self.width, self.width, self.ny)
        z = np.linspace(-self.soil_depth, 0.0, self.nz)
        grid = pv.RectilinearGrid(x, y, z).cast_to_unstructured_grid()
        grid.cell_data["region_name"] = np.array(["soil"] * grid.n_cells)
        grid.field_data["region_name"] = np.array(["soil"])
        return grid

    def _make_wall_volume(self) -> pv.UnstructuredGrid:
        x = np.array([
            -self.length / 2 - self.wall_thickness,
            -self.length / 2,
            self.length / 2,
            self.length / 2 + self.wall_thickness,
        ])
        y = np.array([
            -self.width / 2 - self.wall_thickness,
            -self.width / 2,
            self.width / 2,
            self.width / 2 + self.wall_thickness,
        ])
        z = np.linspace(-self.depth, 0.0, max(4, self.nz // 2))
        grid = pv.RectilinearGrid(x, y, z).cast_to_unstructured_grid()
        centers = grid.cell_centers().points
        inner_x = np.logical_and(centers[:, 0] > -self.length / 2, centers[:, 0] < self.length / 2)
        inner_y = np.logical_and(centers[:, 1] > -self.width / 2, centers[:, 1] < self.width / 2)
        ring_mask = ~(inner_x & inner_y)
        wall = grid.extract_cells(np.where(ring_mask)[0]).cast_to_unstructured_grid()
        wall.cell_data["region_name"] = np.array(["wall"] * wall.n_cells)
        wall.field_data["region_name"] = np.array(["wall"])
        return wall

    def build(self) -> pv.MultiBlock:
        root = SceneNode("pit")
        soil = self._make_structured_soil()
        root.add(SceneNode("soil", soil, metadata={"region": "soil"}))
        wall = self._make_wall_volume()
        root.add(SceneNode("retaining_wall", wall, metadata={"region": "wall"}))
        return root.to_multiblock()
