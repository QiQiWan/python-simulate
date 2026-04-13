import numpy as np

from geoai_simkit.solver.hex8_nonlinear import NonlinearHex8Solver


def test_line_search_accepts_full_increment_vector():
    solver = object.__new__(NonlinearHex8Solver)

    def _evaluate_state(trial, *args, **kwargs):
        fint = np.zeros_like(trial)
        return np.zeros((trial.size, trial.size)), fint, [], np.zeros((1, 6)), np.zeros(1), np.zeros(1), {}, []

    solver._evaluate_state = _evaluate_state

    u_guess = np.zeros(8, dtype=float)
    free = np.array([1, 3, 4], dtype=np.int64)
    fixed_dofs = np.array([0], dtype=np.int64)
    fixed_values = np.array([2.0], dtype=float)
    target = np.zeros_like(u_guess)
    du_full = np.arange(8, dtype=float)

    best_u, alpha = solver._line_search(
        u_guess=u_guess,
        du=du_full,
        free=free,
        fixed_dofs=fixed_dofs,
        fixed_values=fixed_values,
        target=target,
        rnorm0=1.0,
        u_step_base=np.zeros_like(u_guess),
        base_states=[],
        struct_K=np.zeros((8, 8)),
        interfaces=[],
        local_interface_states={},
        ndof=8,
        n_nodes=0,
    )

    assert alpha == 1.0
    np.testing.assert_allclose(best_u[free], du_full[free])
    assert best_u[0] == 2.0
