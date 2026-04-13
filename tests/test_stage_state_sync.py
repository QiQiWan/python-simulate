from __future__ import annotations

import numpy as np
import pytest

pv = pytest.importorskip('pyvista')

from geoai_simkit.core.model import AnalysisStage, BoundaryCondition, SimulationModel
from geoai_simkit.geometry.parametric import ParametricPitScene
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.hex8_nonlinear import NonlinearSolveResult
from geoai_simkit.solver.structural_elements import build_structural_dof_map
from geoai_simkit.solver.warp_backend import WarpBackend


def test_multistage_state_sync_passes_previous_stage_displacement(monkeypatch) -> None:
    model = SimulationModel(name='stage-sync', mesh=ParametricPitScene(nx=3, ny=3, nz=3).build())
    model.ensure_regions()
    model.add_material('soil', 'mohr_coulomb', E=10e6, nu=0.3, cohesion=10000.0, friction_deg=28.0, dilation_deg=0.0, tensile_strength=0.0, rho=1800.0)
    model.add_material('wall', 'linear_elastic', E=20e9, nu=0.2, rho=2500.0)
    model.add_boundary_condition(BoundaryCondition(name='fix_bottom', kind='displacement', target='bottom', components=(0, 1, 2), values=(0.0, 0.0, 0.0)))
    model.add_stage(AnalysisStage(name='s1', steps=1))
    model.add_stage(AnalysisStage(name='s2', steps=1))

    seen_initials: list[np.ndarray | None] = []

    def fake_solve(self, *args, gp_states=None, interface_states=None, initial_u_nodes=None, initial_rotations=None, **kwargs):
        seen_initials.append(None if initial_u_nodes is None else np.asarray(initial_u_nodes, dtype=float).copy())
        n_nodes = self.submesh.points.shape[0]
        u_nodes = np.full((n_nodes, 3), float(len(seen_initials)), dtype=float)
        return NonlinearSolveResult(
            u_nodes=u_nodes,
            structural_rotations=np.zeros((n_nodes, 3), dtype=float),
            cell_stress=np.zeros((self.submesh.elements.shape[0], 6), dtype=float),
            von_mises=np.zeros(self.submesh.elements.shape[0], dtype=float),
            cell_yield_fraction=np.zeros(self.submesh.elements.shape[0], dtype=float),
            cell_eq_plastic=np.zeros(self.submesh.elements.shape[0], dtype=float),
            gp_states=gp_states if gp_states is not None else [],
            interface_states=interface_states if interface_states is not None else {},
            warnings=[],
            dof_map=build_structural_dof_map([], self.submesh),
            convergence_history=[],
        )

    monkeypatch.setattr('geoai_simkit.solver.warp_backend.NonlinearHex8Solver.solve', fake_solve)

    solved = WarpBackend().solve(model, SolverSettings())
    assert len(seen_initials) == 2
    assert seen_initials[0] is not None
    assert np.allclose(seen_initials[0], 0.0)
    assert seen_initials[1] is not None
    assert np.allclose(seen_initials[1], 1.0)
    assert solved.metadata.get('stage_state_sync') is True
