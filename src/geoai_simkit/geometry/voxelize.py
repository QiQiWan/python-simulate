from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import RegionTag


@dataclass(slots=True)
class VoxelizeOptions:
    cell_size: float | None = None
    dims: tuple[int, int, int] | None = None
    padding: float = 0.0
    surface_only: bool = False


class VoxelMesher:
    """Convert surface-like IFC/scene geometry into a Hex8-friendly volumetric grid.

    The implementation is intentionally conservative:
    - each block is extracted as a surface and voxelized independently
    - region names are propagated from block field-data or block key
    - the result is returned as a MultiBlock of volumetric grids so region tags survive
    """

    def __init__(self, options: VoxelizeOptions | None = None) -> None:
        self.options = options or VoxelizeOptions()

    def voxelize_model(self, model: SimulationModel) -> SimulationModel:
        data = model.mesh
        out = pv.MultiBlock()
        region_tags: list[RegionTag] = []
        cell_offset = 0

        if isinstance(data, pv.MultiBlock):
            items = [(str(key), data[key]) for key in data.keys()]
        else:
            items = [(model.name, data)]

        for key, block in items:
            if block is None or int(block.n_cells) == 0:
                continue
            region_name = self._infer_region_name(key, block)
            vox = self._voxelize_block(block)
            if vox is None or int(vox.n_cells) == 0:
                continue
            vox.cell_data["region_name"] = np.array([region_name] * vox.n_cells)
            vox.field_data["region_name"] = np.array([region_name])
            out[region_name] = vox
            region_tags.append(
                RegionTag(
                    name=region_name,
                    cell_ids=np.arange(cell_offset, cell_offset + vox.n_cells, dtype=np.int64),
                    metadata={"source": key, "voxelized": True},
                )
            )
            cell_offset += vox.n_cells

        model.mesh = out if len(out.keys()) > 1 else next((out[k] for k in out.keys()), model.mesh)
        if region_tags:
            model.region_tags = region_tags
            model.metadata["voxelized"] = True
            model.metadata["voxelize_options"] = {
                "cell_size": self.options.cell_size,
                "dims": self.options.dims,
                "padding": self.options.padding,
            }
        return model

    def _infer_region_name(self, key: str, block: pv.DataSet) -> str:
        if "region_name" in block.field_data and len(block.field_data["region_name"]):
            return str(block.field_data["region_name"][0])
        leaf = key.split("/")[-1]
        return leaf or "region"

    def _voxelize_block(self, block: pv.DataSet) -> pv.UnstructuredGrid | None:
        surf = block.extract_surface().triangulate()
        if surf.n_points < 3 or surf.n_cells == 0:
            return None
        bounds = np.asarray(surf.bounds, dtype=float)
        if self.options.padding:
            bounds[[0, 2, 4]] -= self.options.padding
            bounds[[1, 3, 5]] += self.options.padding
        dx, dy, dz = self._spacing(bounds)
        dims = (
            max(2, int(np.ceil((bounds[1] - bounds[0]) / dx)) + 1),
            max(2, int(np.ceil((bounds[3] - bounds[2]) / dy)) + 1),
            max(2, int(np.ceil((bounds[5] - bounds[4]) / dz)) + 1),
        )
        img = pv.ImageData(
            dimensions=dims,
            spacing=(dx, dy, dz),
            origin=(bounds[0], bounds[2], bounds[4]),
        )
        centers = img.cell_centers()
        try:
            selected = centers.select_enclosed_points(surf, tolerance=0.0, check_surface=False)
            mask = np.asarray(selected.point_data["SelectedPoints"], dtype=bool)
        except Exception:
            # Conservative fallback: keep all cells in the bbox when enclosure tests fail.
            mask = np.ones(img.n_cells, dtype=bool)
        if self.options.surface_only:
            shell = img.extract_surface().triangulate()
            return shell.cast_to_unstructured_grid()
        kept = img.extract_cells(np.where(mask)[0])
        return kept.cast_to_unstructured_grid()

    def _spacing(self, bounds: np.ndarray) -> tuple[float, float, float]:
        if self.options.dims is not None:
            nx, ny, nz = self.options.dims
            dx = max((bounds[1] - bounds[0]) / max(nx, 1), 1e-6)
            dy = max((bounds[3] - bounds[2]) / max(ny, 1), 1e-6)
            dz = max((bounds[5] - bounds[4]) / max(nz, 1), 1e-6)
            return dx, dy, dz
        if self.options.cell_size is not None:
            h = max(float(self.options.cell_size), 1e-6)
            return h, h, h
        ext = np.array([
            max(bounds[1] - bounds[0], 1e-6),
            max(bounds[3] - bounds[2], 1e-6),
            max(bounds[5] - bounds[4], 1e-6),
        ])
        h = float(np.max(ext) / 24.0)
        return h, h, h
