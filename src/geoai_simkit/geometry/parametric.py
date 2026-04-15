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

    def _tag_region(self, grid: pv.UnstructuredGrid, region_name: str) -> pv.UnstructuredGrid:
        tagged = grid.cast_to_unstructured_grid()
        tagged.cell_data['region_name'] = np.array([region_name] * tagged.n_cells)
        tagged.field_data['region_name'] = np.array([region_name])
        return tagged

    def _axis_with_breaks(self, outer_half: float, inner_half: float, thickness: float, approx_count: int) -> np.ndarray:
        approx_count = max(6, int(approx_count))
        anchors = np.array([-outer_half, -inner_half - thickness, -inner_half, 0.0, inner_half, inner_half + thickness, outer_half], dtype=float)
        spans = np.diff(anchors)
        total = float(np.sum(np.abs(spans)))
        coords: list[float] = [float(anchors[0])]
        for start, stop in zip(anchors[:-1], anchors[1:], strict=False):
            span = abs(float(stop - start))
            nseg = max(1, int(round(approx_count * (span / max(total, 1.0e-9)))))
            pts = np.linspace(float(start), float(stop), nseg + 1)
            coords.extend(float(v) for v in pts[1:])
        return np.unique(np.round(np.asarray(coords, dtype=float), decimals=9))

    def _z_axis(self) -> np.ndarray:
        anchors = np.array([-self.soil_depth, -self.depth, -0.75 * self.depth, -self.depth / 2.0, -0.25 * self.depth, 0.0], dtype=float)
        coords: list[float] = [float(anchors[0])]
        spans = np.diff(anchors)
        total = float(np.sum(np.abs(spans)))
        for start, stop in zip(anchors[:-1], anchors[1:], strict=False):
            span = abs(float(stop - start))
            nseg = max(1, int(round(max(6, self.nz) * (span / max(total, 1.0e-9)))))
            pts = np.linspace(float(start), float(stop), nseg + 1)
            coords.extend(float(v) for v in pts[1:])
        return np.unique(np.round(np.asarray(coords, dtype=float), decimals=9))

    def _base_grid(self) -> pv.UnstructuredGrid:
        x = self._axis_with_breaks(self.length, self.length / 2.0, self.wall_thickness, self.nx)
        y = self._axis_with_breaks(self.width, self.width / 2.0, self.wall_thickness, self.ny)
        z = self._z_axis()
        return pv.RectilinearGrid(x, y, z).cast_to_unstructured_grid()

    def _split_regions(self) -> dict[str, pv.UnstructuredGrid]:
        grid = self._base_grid()
        centers = grid.cell_centers().points
        tol = 1.0e-9
        pit_x = self.length / 2.0
        pit_y = self.width / 2.0
        wall_t = self.wall_thickness

        inside_pit = (
            (np.abs(centers[:, 0]) < pit_x - tol)
            & (np.abs(centers[:, 1]) < pit_y - tol)
            & (centers[:, 2] > -self.depth - tol)
        )
        wall_ring = (
            (centers[:, 2] > -self.depth - tol)
            & (
                (
                    (np.abs(centers[:, 0]) >= pit_x - tol)
                    & (np.abs(centers[:, 0]) <= pit_x + wall_t + tol)
                    & (np.abs(centers[:, 1]) <= pit_y + wall_t + tol)
                )
                | (
                    (np.abs(centers[:, 1]) >= pit_y - tol)
                    & (np.abs(centers[:, 1]) <= pit_y + wall_t + tol)
                    & (np.abs(centers[:, 0]) <= pit_x + wall_t + tol)
                )
            )
        )
        exc1 = inside_pit & (centers[:, 2] >= -self.depth / 2.0 - tol)
        exc2 = inside_pit & (centers[:, 2] < -self.depth / 2.0 - tol)
        soil_mass = ~(wall_ring | exc1 | exc2)

        parts: dict[str, pv.UnstructuredGrid] = {}
        for region_name, mask in {
            'soil_mass': soil_mass,
            'soil_excavation_1': exc1,
            'soil_excavation_2': exc2,
            'wall': wall_ring,
        }.items():
            ids = np.where(mask)[0]
            if ids.size == 0:
                continue
            parts[region_name] = self._tag_region(grid.extract_cells(ids).cast_to_unstructured_grid(), region_name)
        return parts

    def build(self) -> pv.MultiBlock:
        root = SceneNode('pit')
        regions = self._split_regions()
        for region_name in ('soil_mass', 'soil_excavation_1', 'soil_excavation_2'):
            grid = regions.get(region_name)
            if grid is None:
                continue
            root.add(SceneNode(region_name, grid, metadata={'region': region_name, 'role': 'soil'}))
        wall = regions.get('wall')
        if wall is not None:
            root.add(SceneNode('retaining_wall', wall, metadata={'region': 'wall', 'role': 'wall'}))
        return root.to_multiblock()
