from __future__ import annotations

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel


POINT_PERSIST = {"X0", "Z0"}
CELL_PERSIST = {"region_name"}


def build_stage_dataset(model: SimulationModel, stage: str | None, displacement_scale: float = 1.0) -> pv.DataSet:
    """Build a dataset containing only the results relevant to one stage.

    If the solver stored original coordinates in `X0`, stage displacements are applied
    to reconstruct a stage-specific deformed geometry.
    """
    data = model.to_unstructured_grid().copy(deep=True)
    _clear_nonpersistent_arrays(data)

    for field in model.results:
        if field.stage != stage:
            continue
        if field.association == "point":
            data.point_data[field.name] = np.asarray(field.values)
        elif field.association == "cell":
            data.cell_data[field.name] = np.asarray(field.values)

    if "X0" in data.point_data and stage is not None and "U" in data.point_data:
        x0 = np.asarray(data.point_data["X0"], dtype=float)
        u = np.asarray(data.point_data["U"], dtype=float)
        if x0.shape == u.shape:
            data.points = x0 + displacement_scale * u
    return data


def _clear_nonpersistent_arrays(data: pv.DataSet) -> None:
    for name in list(data.point_data.keys()):
        if name not in POINT_PERSIST:
            del data.point_data[name]
    for name in list(data.cell_data.keys()):
        if name not in CELL_PERSIST:
            del data.cell_data[name]
