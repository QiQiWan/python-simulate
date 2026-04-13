from __future__ import annotations

from collections.abc import Iterable

import numpy as np
try:
    import pyvista as pv
except ModuleNotFoundError:  # pragma: no cover
    class _DummyDataSet:
        pass
    class _DummyMultiBlock:
        pass
    class _DummyUnstructuredGrid:
        pass
    class _PVStub:
        DataSet = _DummyDataSet
        MultiBlock = _DummyMultiBlock
        UnstructuredGrid = _DummyUnstructuredGrid
    pv = _PVStub()

from geoai_simkit.core.types import RegionTag


def infer_region_name(block_name: str, block: pv.DataSet) -> str:
    if isinstance(block, pv.DataSet):
        if "region_name" in block.field_data and len(block.field_data["region_name"]):
            return str(block.field_data["region_name"][0])
    leaf = block_name.split("/")[-1]
    return leaf


def build_region_tags_from_mesh(mesh: pv.DataSet | pv.MultiBlock) -> list[RegionTag]:
    if isinstance(mesh, pv.MultiBlock):
        tags: list[RegionTag] = []
        offset = 0
        for key in mesh.keys():
            block = mesh[key]
            if block is None:
                continue
            region_name = infer_region_name(str(key), block)
            n_cells = int(block.n_cells)
            if n_cells <= 0:
                continue
            cell_ids = np.arange(offset, offset + n_cells, dtype=np.int64)
            tags.append(RegionTag(name=region_name, cell_ids=cell_ids, metadata={"source": str(key)}))
            offset += n_cells
        return tags

    if "region_name" in mesh.cell_data:
        names = np.asarray(mesh.cell_data["region_name"])
        tags = []
        for name in np.unique(names):
            mask = np.where(names == name)[0].astype(np.int64)
            tags.append(RegionTag(name=str(name), cell_ids=mask, metadata={"source": "cell_data"}))
        return tags
    return []
