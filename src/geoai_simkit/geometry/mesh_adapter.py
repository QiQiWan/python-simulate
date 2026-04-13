from __future__ import annotations

import numpy as np
import pyvista as pv


def to_unstructured_grid(data: pv.DataSet | pv.MultiBlock) -> pv.UnstructuredGrid:
    if isinstance(data, pv.MultiBlock):
        return data.combine().cast_to_unstructured_grid()
    if isinstance(data, pv.UnstructuredGrid):
        return data.copy(deep=True)
    return data.cast_to_unstructured_grid()


def add_region_arrays(grid: pv.UnstructuredGrid, region_name: str, cell_ids: np.ndarray) -> None:
    mask = np.zeros(grid.n_cells, dtype=np.int32)
    mask[cell_ids] = 1
    grid.cell_data[f"region::{region_name}"] = mask


def ensure_point_vector(grid: pv.UnstructuredGrid, name: str, fill: float = 0.0) -> None:
    if name not in grid.point_data:
        grid.point_data[name] = np.full((grid.n_points, 3), fill, dtype=float)
