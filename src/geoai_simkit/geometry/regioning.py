from __future__ import annotations

from collections.abc import Iterable

import numpy as np


class _DummyDataSet:  # pragma: no cover
    pass


class _DummyMultiBlock:  # pragma: no cover
    pass


class _DummyUnstructuredGrid:  # pragma: no cover
    pass


class _PVStub:  # pragma: no cover
    DataSet = _DummyDataSet
    MultiBlock = _DummyMultiBlock
    UnstructuredGrid = _DummyUnstructuredGrid


pv = _PVStub()


def _is_multiblock_mesh(mesh) -> bool:
    if mesh is None:
        return False
    if type(mesh).__name__.lower() == 'multiblock':
        return True
    return bool(hasattr(mesh, 'combine') and hasattr(mesh, 'keys') and not hasattr(mesh, 'get_cell'))


def _is_dataset_like(block) -> bool:
    return bool(block is not None and (hasattr(block, 'cell_data') or hasattr(block, 'field_data') or hasattr(block, 'n_cells')))

from geoai_simkit.core.types import RegionTag


def infer_region_name(block_name: str, block: pv.DataSet) -> str:
    if _is_dataset_like(block):
        if "region_name" in block.field_data and len(block.field_data["region_name"]):
            return str(block.field_data["region_name"][0])
        if "region_name" in block.cell_data:
            names = np.asarray(block.cell_data["region_name"])
            unique = np.unique(names)
            if unique.size == 1:
                return str(unique[0])
    leaf = block_name.split("/")[-1]
    return leaf


def build_region_tags_from_mesh(mesh: pv.DataSet | pv.MultiBlock) -> list[RegionTag]:
    if _is_multiblock_mesh(mesh):
        tags: list[RegionTag] = []
        offset = 0
        for key in mesh.keys():
            block = mesh[key]
            if block is None:
                continue
            n_cells = int(block.n_cells)
            if n_cells <= 0:
                continue
            if "region_name" in getattr(block, 'cell_data', {}):
                names = np.asarray(block.cell_data["region_name"])
                if names.size == n_cells:
                    for name in np.unique(names):
                        local_ids = np.where(names == name)[0].astype(np.int64)
                        if local_ids.size == 0:
                            continue
                        tags.append(RegionTag(name=str(name), cell_ids=(offset + local_ids).astype(np.int64), metadata={"source": str(key), "source_kind": "cell_data"}))
                    offset += n_cells
                    continue
            region_name = infer_region_name(str(key), block)
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
