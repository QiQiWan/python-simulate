from __future__ import annotations

import pytest

pv = pytest.importorskip("pyvista")

import numpy as np

from geoai_simkit.core.model import BoundaryCondition, SimulationModel
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.warp_backend import WarpBackend


def test_linear_hex8_solver_produces_displacement_field() -> None:
    model = SimulationModel(name="hex8-test", mesh=ParametricPitScene(nx=5, ny=5, nz=5).build())
    model.ensure_regions()
    model.add_material("soil", "linear_elastic", E=10e6, nu=0.3, rho=1800.0)
    model.add_material("wall", "linear_elastic", E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name="fix_bottom", kind="displacement", target="bottom", components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    solved = WarpBackend().solve(model, SolverSettings())
    assert solved.metadata["solver_mode"] == "linear-hex8"
    assert "U" in solved.mesh.point_data
    u = np.asarray(solved.mesh.point_data["U"])
    assert u.shape[1] == 3
    assert np.min(u[:, 2]) <= 0.0