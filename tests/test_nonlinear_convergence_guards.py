from __future__ import annotations

import numpy as np

from geoai_simkit.materials.linear_elastic import LinearElastic
from geoai_simkit.solver.hex8_linear import Hex8Submesh
from geoai_simkit.solver.hex8_nonlinear import NonlinearHex8Solver


def _make_solver() -> NonlinearHex8Solver:
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ], dtype=float)
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int32)
    submesh = Hex8Submesh(points=points, elements=elements, full_cell_ids=np.array([0], dtype=np.int32), global_point_ids=np.arange(8, dtype=np.int32), local_by_global={i: i for i in range(8)})
    mats = [LinearElastic(E=1.0e5, nu=0.3, rho=1800.0)]
    return NonlinearHex8Solver(submesh, mats, gravity=(0.0, 0.0, 0.0))


def test_nonconverged_step_aborts_instead_of_advancing(monkeypatch) -> None:
    solver = _make_solver()

    def fake_dirichlet(*args, **kwargs):
        return np.array([0], dtype=np.int64), np.array([0.0], dtype=float)

    def fake_external(*args, **kwargs):
        return np.ones(24, dtype=float)

    def fake_evaluate(u_guess, *args, **kwargs):
        ndof = u_guess.size
        fint = np.zeros(ndof, dtype=float)
        # keep residual constant and large so the step never converges
        return np.eye(ndof), fint, [[solver.materials[0].create_state() for _ in range(8)]], np.zeros((1, 6)), np.zeros(1), np.zeros(1), {}, []

    monkeypatch.setattr(solver, '_dirichlet_data', fake_dirichlet)
    monkeypatch.setattr(solver, '_build_external_force', fake_external)
    monkeypatch.setattr(solver, '_evaluate_state', fake_evaluate)

    result = solver.solve(
        bcs=(),
        loads=(),
        n_steps=2,
        max_iterations=4,
        tolerance=1.0e-8,
        line_search=False,
        max_cutbacks=1,
        solver_metadata={'abort_on_step_failure': True, 'max_total_steps': 8, 'min_load_increment': 1.0e-3},
    )

    assert result.converged is False
    assert result.completed_lambda < 1.0
    assert any('failed to converge' in str(w) or 'Stagnation detected' in str(w) for w in result.warnings)


def test_nonconverged_step_can_still_cut_back(monkeypatch) -> None:
    solver = _make_solver()

    def fake_dirichlet(*args, **kwargs):
        return np.array([0], dtype=np.int64), np.array([0.0], dtype=float)

    def fake_external(*args, **kwargs):
        return np.ones(24, dtype=float)

    call_counter = {'n': 0}

    def fake_evaluate(u_guess, *args, **kwargs):
        call_counter['n'] += 1
        ndof = u_guess.size
        fint = np.zeros(ndof, dtype=float)
        return np.eye(ndof), fint, [[solver.materials[0].create_state() for _ in range(8)]], np.zeros((1, 6)), np.zeros(1), np.zeros(1), {}, []

    monkeypatch.setattr(solver, '_dirichlet_data', fake_dirichlet)
    monkeypatch.setattr(solver, '_build_external_force', fake_external)
    monkeypatch.setattr(solver, '_evaluate_state', fake_evaluate)

    result = solver.solve(
        bcs=(),
        loads=(),
        n_steps=2,
        max_iterations=4,
        tolerance=1.0e-8,
        line_search=False,
        max_cutbacks=2,
        solver_metadata={'abort_on_step_failure': False, 'max_total_steps': 6, 'min_load_increment': 0.2},
    )

    assert result.total_steps_taken <= 6
    assert call_counter['n'] > 0
