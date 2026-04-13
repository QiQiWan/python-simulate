from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.linear_algebra import configure_linear_algebra_threads


def test_solver_settings_support_thread_count():
    s = SolverSettings(thread_count=4)
    assert s.thread_count == 4


def test_configure_linear_algebra_threads_returns_requested_value():
    assert configure_linear_algebra_threads(3) == 3
