import pytest
pv = pytest.importorskip('pyvista')
import numpy as np

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import RegionTag
from geoai_simkit.app.mesh_check import analyze_mesh


def test_analyze_mesh_quality_flags_degenerate_hex():
    pts = np.array([
        [0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,0],[1,0,0],[1,1,0],[0,1,0]
    ], dtype=float)
    cells = np.hstack([[8,0,1,2,3,4,5,6,7]]).astype(np.int64)
    grid = pv.UnstructuredGrid(cells, np.array([pv.CellType.HEXAHEDRON], dtype=np.uint8), pts)
    model = SimulationModel(name='m', mesh=grid, region_tags=[RegionTag(name='r1', cell_ids=np.array([0], dtype=np.int64))])
    report = analyze_mesh(model)
    assert report.n_cells == 1
    assert report.bad_cell_ids == [0]
    assert report.regions[0].bad_cells == 1
