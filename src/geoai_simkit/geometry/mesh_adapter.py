from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    pv = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import pyvista as _pv


def _require_pyvista() -> Any:
    if pv is None:
        raise ModuleNotFoundError(
            'pyvista is required for mesh adaptation utilities. '
            'Install the geometry/visualization dependencies to use this path.'
        )
    return pv


def to_unstructured_grid(data: Any) -> Any:
    module = _require_pyvista()
    if isinstance(data, module.MultiBlock):
        return data.combine(merge_points=True).cast_to_unstructured_grid()
    if isinstance(data, module.UnstructuredGrid):
        return data.copy(deep=True)
    return data.cast_to_unstructured_grid()


def add_region_arrays(grid: Any, region_name: str, cell_ids: np.ndarray) -> None:
    mask = np.zeros(int(grid.n_cells), dtype=np.int32)
    mask[np.asarray(cell_ids, dtype=np.int64)] = 1
    grid.cell_data[f'region::{region_name}'] = mask


def ensure_point_vector(grid: Any, name: str, fill: float = 0.0) -> None:
    if name not in grid.point_data:
        grid.point_data[name] = np.full((int(grid.n_points), 3), fill, dtype=float)
