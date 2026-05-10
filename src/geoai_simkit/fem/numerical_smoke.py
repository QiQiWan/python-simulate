from __future__ import annotations
from typing import Any
import math
import numpy as np

def _row(key: str, ok: bool, value: Any = None, expected: Any = None, **meta: Any) -> dict[str, Any]:
    return {'key': key, 'ok': bool(ok), 'value': value, 'expected': expected, 'status': 'numerical_smoke', **meta}

def run_geometry_smoke() -> dict[str, Any]:
    coords = np.array([[0,0,0],[2,0,0],[2,1,0],[0,1,0]], dtype=float)
    area = 0.5 * abs(np.dot(coords[:,0], np.roll(coords[:,1], -1)) - np.dot(coords[:,1], np.roll(coords[:,0], -1)))
    return _row('geometry', abs(area - 2.0) < 1e-12, area, 2.0, metric='quad_area')

def run_mesh_smoke() -> dict[str, Any]:
    x = np.linspace(0.0, 1.0, 3)
    h = float(np.diff(x).mean())
    quality = min(np.diff(x)) / max(np.diff(x))
    return _row('mesh', abs(h - 0.5) < 1e-12 and abs(quality - 1.0) < 1e-12, {'h':h,'quality':quality}, {'h':0.5,'quality':1.0})

def run_material_smoke() -> dict[str, Any]:
    E = 1000.0; nu = 0.25; strain = np.array([1e-3, 0.0, 0.0])
    coef = E / ((1 + nu) * (1 - 2 * nu))
    D = coef * np.array([[1-nu,nu,nu],[nu,1-nu,nu],[nu,nu,1-nu]])
    stress = D @ strain
    return _row('material', np.allclose(stress, [1.2,0.4,0.4]), stress.tolist(), [1.2,0.4,0.4], metric='linear_elastic_3d')

def run_element_smoke() -> dict[str, Any]:
    # 1D bar element stiffness with E=A=L=1 has [[1,-1],[-1,1]].
    k = np.array([[1.0,-1.0],[-1.0,1.0]])
    eig = np.linalg.eigvalsh(k)
    return _row('element', np.allclose(eig, [0.0,2.0]), eig.tolist(), [0.0,2.0], metric='bar_eigenvalues')

def run_assembly_smoke() -> dict[str, Any]:
    k = np.zeros((3,3)); ke = np.array([[1.0,-1.0],[-1.0,1.0]])
    for a,b in [(0,1),(1,2)]: k[np.ix_([a,b],[a,b])] += ke
    return _row('assembly', np.allclose(k, [[1,-1,0],[-1,2,-1],[0,-1,1]]), k.tolist(), '3-node chain stiffness')

def run_solver_smoke() -> dict[str, Any]:
    K = np.array([[2.0,-1.0],[-1.0,2.0]]); f = np.array([1.0,0.0])
    u = np.linalg.solve(K, f)
    r = np.linalg.norm(K @ u - f)
    return _row('solver', r < 1e-12 and np.allclose(u, [2/3, 1/3]), u.tolist(), [2/3,1/3], residual=float(r))

def run_result_smoke() -> dict[str, Any]:
    values = np.array([0.0, 0.1, 0.3, 0.2])
    peak = float(values.max()); idx = int(values.argmax())
    return _row('result', peak == 0.3 and idx == 2, {'peak': peak, 'argmax': idx}, {'peak':0.3,'argmax':2})

RUNNERS = {
    'geometry': run_geometry_smoke,
    'mesh': run_mesh_smoke,
    'material': run_material_smoke,
    'element': run_element_smoke,
    'assembly': run_assembly_smoke,
    'solver': run_solver_smoke,
    'result': run_result_smoke,
}

def run_single_smoke(key: str) -> dict[str, Any]:
    return RUNNERS[str(key)]()

def run_core_numerical_smoke() -> dict[str, Any]:
    checks = [fn() for fn in RUNNERS.values()]
    return {'suite': 'core_fem_numerical_smoke', 'ok': all(c['ok'] for c in checks), 'passed_count': sum(1 for c in checks if c['ok']), 'check_count': len(checks), 'checks': checks}
