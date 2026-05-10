from __future__ import annotations

from dataclasses import dataclass, field

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
    block_splits: tuple[dict[str, object], ...] | list[dict[str, object]] = field(default_factory=tuple)

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



    def _split_grid_by_plane(self, grid: pv.UnstructuredGrid, *, axis: str, coordinate: float, negative_name: str, positive_name: str) -> dict[str, pv.UnstructuredGrid]:
        axis_key = str(axis or 'x').strip().lower()
        axis_index = {'x': 0, 'y': 1, 'z': 2}.get(axis_key, 0)
        centers = grid.cell_centers().points
        tol = 1.0e-9
        negative_ids = np.where(centers[:, axis_index] < float(coordinate) - tol)[0]
        positive_ids = np.where(centers[:, axis_index] >= float(coordinate) - tol)[0]
        if negative_ids.size == 0 or positive_ids.size == 0:
            return {negative_name if negative_ids.size else positive_name: self._tag_region(grid, negative_name if negative_ids.size else positive_name)}
        return {
            negative_name: self._tag_region(grid.extract_cells(negative_ids).cast_to_unstructured_grid(), negative_name),
            positive_name: self._tag_region(grid.extract_cells(positive_ids).cast_to_unstructured_grid(), positive_name),
        }

    def _split_grid_by_box(self, grid: pv.UnstructuredGrid, *, bounds: tuple[float, float, float, float, float, float], inside_name: str, outside_name: str) -> dict[str, pv.UnstructuredGrid]:
        centers = grid.cell_centers().points
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]
        inside_mask = (
            (centers[:, 0] >= xmin) & (centers[:, 0] <= xmax)
            & (centers[:, 1] >= ymin) & (centers[:, 1] <= ymax)
            & (centers[:, 2] >= zmin) & (centers[:, 2] <= zmax)
        )
        inside_ids = np.where(inside_mask)[0]
        outside_ids = np.where(~inside_mask)[0]
        if inside_ids.size == 0 or outside_ids.size == 0:
            return {outside_name if outside_ids.size else inside_name: self._tag_region(grid, outside_name if outside_ids.size else inside_name)}
        return {
            inside_name: self._tag_region(grid.extract_cells(inside_ids).cast_to_unstructured_grid(), inside_name),
            outside_name: self._tag_region(grid.extract_cells(outside_ids).cast_to_unstructured_grid(), outside_name),
        }

    def _normalized_split_definitions(self) -> list[dict[str, object]]:
        items = list(self.block_splits or ())
        normalized: list[dict[str, object]] = []
        for index, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                continue
            target = str(raw.get('target_block') or raw.get('region_name') or raw.get('target') or '').strip()
            if not target:
                continue
            kind = str(raw.get('kind') or 'surface').strip().lower() or 'surface'
            name = str(raw.get('name') or f'{target}__split_{index:02d}').strip()
            normalized.append({'name': name, 'target_block': target, **dict(raw), 'kind': kind})
        return normalized

    def _default_box_bounds(self, grid: pv.UnstructuredGrid) -> tuple[float, float, float, float, float, float]:
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in grid.bounds]
        dx = max((xmax - xmin) * 0.2, 1.0e-6)
        dy = max((ymax - ymin) * 0.2, 1.0e-6)
        dz = max((zmax - zmin) * 0.2, 1.0e-6)
        return (xmin + dx, xmax - dx, ymin + dy, ymax - dy, zmin + dz, zmax - dz)

    def _apply_block_splits(self, parts: dict[str, pv.UnstructuredGrid]) -> dict[str, pv.UnstructuredGrid]:
        if not self.block_splits:
            return parts
        output: dict[str, pv.UnstructuredGrid] = dict(parts)
        for split_index, item in enumerate(self._normalized_split_definitions(), start=1):
            target = str(item.get('target_block') or '')
            source = output.pop(target, None)
            if source is None:
                continue
            kind = str(item.get('kind') or 'surface').strip().lower()
            name = str(item.get('name') or f'{target}__split_{split_index:02d}')
            if kind in {'point', 'line', 'surface'}:
                default_axis = {'point': 'x', 'line': 'y', 'surface': 'z'}.get(kind, 'x')
                axis = str(item.get('axis') or default_axis)
                if item.get('coordinate') is None:
                    bounds = [float(v) for v in source.bounds]
                    axis_index = {'x': 0, 'y': 1, 'z': 2}.get(axis.strip().lower(), 0)
                    coordinate = 0.5 * (bounds[2 * axis_index] + bounds[2 * axis_index + 1])
                else:
                    coordinate = float(item.get('coordinate', 0.0) or 0.0)
                negative_name = str(item.get('negative_name') or f'{name}__neg')
                positive_name = str(item.get('positive_name') or f'{name}__pos')
                output.update(self._split_grid_by_plane(source, axis=axis, coordinate=coordinate, negative_name=negative_name, positive_name=positive_name))
            elif kind == 'solid':
                bounds_raw = item.get('bounds') or item.get('box_bounds')
                if isinstance(bounds_raw, (list, tuple)) and len(bounds_raw) >= 6:
                    bounds = tuple(float(v) for v in list(bounds_raw)[:6])
                else:
                    bounds = self._default_box_bounds(source)
                inside_name = str(item.get('inside_name') or f'{name}__inside')
                outside_name = str(item.get('outside_name') or f'{name}__outside')
                output.update(self._split_grid_by_box(source, bounds=bounds, inside_name=inside_name, outside_name=outside_name))
            else:
                output[target] = source
        return output

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
        return self._apply_block_splits(parts)

    def build(self) -> pv.MultiBlock:
        root = SceneNode('pit')
        regions = self._split_regions()
        for region_name, grid in regions.items():
            role = 'wall' if 'wall' in region_name else 'soil'
            node_name = 'retaining_wall' if region_name == 'wall' else region_name
            root.add(SceneNode(node_name, grid, metadata={'region': region_name, 'role': role}))
        return root.to_multiblock()
