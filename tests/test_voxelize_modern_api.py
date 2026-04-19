from __future__ import annotations

import numpy as np
import pytest

pv = pytest.importorskip('pyvista')

from geoai_simkit.geometry.voxelize import VoxelMesher, VoxelizeOptions


class _Selected:
    def __init__(self, n: int) -> None:
        self.point_data = {'SelectedPoints': np.ones(n, dtype=np.uint8)}


class _Centers:
    def __init__(self, n: int) -> None:
        self.used_modern_api = False
        self.n = n

    def select_interior_points(self, surf, tolerance=0.0, check_surface=False):
        self.used_modern_api = True
        return _Selected(self.n)


class _Image:
    def __init__(self, dimensions, spacing, origin) -> None:
        self.n_cells = max(1, (dimensions[0] - 1) * (dimensions[1] - 1) * (dimensions[2] - 1))
        self.centers = _Centers(self.n_cells)

    def cell_centers(self):
        return self.centers

    def extract_cells(self, ids):
        pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]])
        cells = np.hstack([[8, 0, 1, 2, 3, 4, 5, 6, 7]])
        return pv.UnstructuredGrid(cells, np.array([pv.CellType.HEXAHEDRON], dtype=np.uint8), pts)


class _Surface:
    n_points = 8
    n_cells = 6
    bounds = (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)

    def triangulate(self):
        return self


class _Block:
    def __init__(self) -> None:
        self.algorithm = None

    def extract_surface(self, algorithm=None):
        self.algorithm = algorithm
        return _Surface()


def test_voxelizer_uses_explicit_surface_algorithm_and_modern_point_selection(monkeypatch) -> None:
    created_images = []
    monkeypatch.setattr(pv, 'ImageData', lambda *, dimensions, spacing, origin: created_images.append(_Image(dimensions, spacing, origin)) or created_images[-1])
    block = _Block()
    grid, info = VoxelMesher(VoxelizeOptions(cell_size=0.5))._voxelize_block(block, object_name='dummy')
    assert block.algorithm == 'dataset_surface'
    assert created_images[0].centers.used_modern_api is True
    assert int(grid.n_cells) > 0 and info['selected_cells'] > 0
