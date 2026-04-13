from geoai_simkit.solver.base import SolverSettings


def test_solver_settings_accepts_max_iterations():
    s = SolverSettings(max_iterations=24, prefer_sparse=False)
    assert s.max_iterations == 24
    assert s.metadata["max_nonlinear_iterations"] == 24
