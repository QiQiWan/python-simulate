from __future__ import annotations

import numpy as np

from geoai_simkit.materials import MaterialState
from geoai_simkit.solver.hex8_nonlinear import NonlinearHex8Solver
from geoai_simkit.solver.structural_elements import StructuralAssemblyResult, StructuralDofMap


def test_evaluate_state_accepts_structural_assembly_result() -> None:
    solver = NonlinearHex8Solver.__new__(NonlinearHex8Solver)
    solver.submesh = type('Sub', (), {'points': np.zeros((1, 3), dtype=float), 'elements': np.zeros((0, 8), dtype=np.int64)})()
    solver._current_compute_device = 'cpu'
    solver._current_solver_metadata = {}
    solver._sp = None
    def _assemble(*args, **kwargs):
        return np.zeros((3, 3), dtype=float), np.zeros(3, dtype=float), [[]], np.zeros((0, 6), dtype=float), np.zeros(0, dtype=float), np.zeros(0, dtype=float)
    solver._assemble_continuum_response = _assemble
    u = np.array([0.1, 0.0, 0.0])
    struct = StructuralAssemblyResult(
        K=np.eye(3, dtype=float) * 2.0,
        F=np.zeros(3, dtype=float),
        count=1,
        warnings=[],
        dof_map=StructuralDofMap(trans_ndof=3, total_ndof=3, rot_base=3, rot_by_local_node={}),
    )
    K, Fint, *_ = solver._evaluate_state(u, np.zeros(3, dtype=float), [[]], struct, [], {}, 3, 1, assemble_tangent=True)
    assert np.allclose(Fint, np.array([0.2, 0.0, 0.0]))
    assert np.allclose(K, np.eye(3, dtype=float) * 2.0)
