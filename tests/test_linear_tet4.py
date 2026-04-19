from __future__ import annotations

import pytest

pv = pytest.importorskip('pyvista')

import numpy as np

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, SimulationModel
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.tet4_linear import extract_tet4_submesh, subset_tet4_submesh
from geoai_simkit.solver.warp_backend import WarpBackend


def _single_tet_grid() -> pv.UnstructuredGrid:
    points = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=float)
    cells = np.asarray([4, 0, 1, 2, 3], dtype=np.int64)
    celltypes = np.asarray([int(pv.CellType.TETRA)], dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells, celltypes, points)
    grid.cell_data['region_name'] = np.asarray(['soil'])
    return grid


def test_extract_tet4_submesh_handles_basic_tetra_cell() -> None:
    grid = _single_tet_grid()
    sub = extract_tet4_submesh(grid)
    assert sub.elements.shape == (1, 4)
    assert sub.points.shape == (4, 3)
    assert sub.full_cell_ids.tolist() == [0]
    sliced = subset_tet4_submesh(sub, np.asarray([True]))
    assert sliced.elements.shape == (1, 4)


def test_linear_tet4_solver_produces_displacement_field() -> None:
    model = SimulationModel(name='tet4-test', mesh=_single_tet_grid())
    model.ensure_regions()
    model.add_material('soil', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    solved = WarpBackend().solve(model, SolverSettings())
    assert solved.metadata['solver_mode'] == 'linear-tet4'
    assert 'U' in solved.mesh.point_data
    u = np.asarray(solved.mesh.point_data['U'])
    assert u.shape == (4, 3)
    assert float(u[3, 2]) <= 0.0


def test_linear_tet4_solver_respects_stage_region_filtering() -> None:
    model = SimulationModel(name='tet4-stage', mesh=_single_tet_grid())
    model.ensure_regions()
    model.add_material('soil', 'linear_elastic', E=10e6, nu=0.3, rho=1800.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    model.add_stage(AnalysisStage(name='empty_stage', deactivate_regions=('soil',)))
    model.add_stage(AnalysisStage(name='soil_stage', activate_regions=('soil',)))
    solved = WarpBackend().solve(model, SolverSettings())
    warnings = solved.metadata.get('solver_warnings', [])
    assert any('no active Tet4 cells' in str(item) for item in warnings)
    assert solved.metadata['stages_run'] == ['empty_stage', 'soil_stage']
