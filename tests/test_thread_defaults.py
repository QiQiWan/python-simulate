from geoai_simkit.solver.linear_algebra import default_thread_count, configure_linear_algebra_threads


def test_default_thread_count_positive():
    assert default_thread_count() >= 1


def test_configure_linear_algebra_threads_auto_uses_default():
    assert configure_linear_algebra_threads(0) == default_thread_count()
