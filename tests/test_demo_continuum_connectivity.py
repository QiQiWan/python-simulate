from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pyvista")

from geoai_simkit.examples.pit_example import build_demo_model
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def test_multiblock_demo_mesh_merges_shared_points_for_solver_topology() -> None:
    model = build_demo_model()
    grid = model.to_unstructured_grid()
    pts = np.asarray(grid.points, dtype=float)
    unique = np.unique(np.round(pts, 9), axis=0)
    assert unique.shape[0] == pts.shape[0]


def test_demo_linearized_run_produces_bounded_displacements() -> None:
    model = build_demo_model()
    solved = WarpBackend().solve(model, SolverSettings(prefer_sparse=True, line_search=True, max_cutbacks=5))
    u = solved.field_for("U", "initial")
    assert u is not None
    u_mag = np.linalg.norm(np.asarray(u.values, dtype=float), axis=1)
    assert float(np.max(u_mag)) < 1.0
