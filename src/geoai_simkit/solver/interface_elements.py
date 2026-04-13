from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from geoai_simkit.core.model import InterfaceDefinition
from geoai_simkit.solver.hex8_linear import Hex8Submesh


@dataclass(slots=True)
class InterfaceAssemblyResult:
    K: np.ndarray
    Fint: np.ndarray
    count: int
    warnings: list[str]


@dataclass(slots=True)
class InterfaceElementState:
    slip: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    closed: bool = False
    traction: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))


def _edofs_pair(ls: int, lm: int) -> np.ndarray:
    return np.array([3 * ls, 3 * ls + 1, 3 * ls + 2, 3 * lm, 3 * lm + 1, 3 * lm + 2], dtype=np.int64)


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        raise ValueError("Zero-length normal in interface element")
    return v / n


def _pair_stiffness(
    kn: float,
    ks: float,
    normal: np.ndarray,
    sliding: bool,
) -> np.ndarray:
    I = np.eye(3)
    Pn = np.outer(normal, normal)
    Pt = I - Pn
    kt = ks if not sliding else max(1e-6 * ks, 1e-9)
    K3 = kn * Pn + kt * Pt
    return np.block([[K3, -K3], [-K3, K3]])


def interface_pair_response(
    x_slave: np.ndarray,
    x_master: np.ndarray,
    u_slave: np.ndarray,
    u_master: np.ndarray,
    params: dict,
    state: InterfaceElementState | None = None,
) -> tuple[np.ndarray, np.ndarray, InterfaceElementState]:
    if state is None:
        state = InterfaceElementState()
    kn = float(params.get("kn", 1.0e8))
    ks = float(params.get("ks", 1.0e7))
    mu = np.tan(np.deg2rad(float(params.get("friction_deg", 25.0))))
    n = params.get("normal")
    if n is None:
        d0 = x_slave - x_master
        if np.linalg.norm(d0) < 1e-12:
            n = np.array([0.0, 0.0, 1.0], dtype=float)
        else:
            n = d0
    normal = _unit(np.asarray(n, dtype=float))
    rel = (x_slave + u_slave) - (x_master + u_master)
    gap_n = float(np.dot(rel, normal))
    if gap_n > 0.0:
        state.closed = False
        state.slip = np.zeros(3, dtype=float)
        state.traction = np.zeros(3, dtype=float)
        return np.zeros((6, 6), dtype=float), np.zeros(6, dtype=float), state

    closed_pen = -gap_n
    rel_t = rel - gap_n * normal
    t_trial = ks * rel_t
    t_n = kn * closed_pen
    t_t_norm = float(np.linalg.norm(t_trial))
    sliding = t_t_norm > mu * t_n and t_t_norm > 1e-12
    if sliding:
        t_t = t_trial / t_t_norm * (mu * t_n)
    else:
        t_t = t_trial
    traction = t_t - t_n * normal
    fint = np.hstack([traction, -traction])
    K = _pair_stiffness(kn, ks, normal, sliding=sliding)
    state.closed = True
    state.slip = rel_t.copy()
    state.traction = traction.copy()
    return K, fint, state


def assemble_interface_response(
    interfaces: list[InterfaceDefinition],
    submesh: Hex8Submesh,
    u_nodes: np.ndarray,
    state_store: dict[str, list[InterfaceElementState]] | None = None,
) -> tuple[InterfaceAssemblyResult, dict[str, list[InterfaceElementState]]]:
    ndof = submesh.points.shape[0] * 3
    K = np.zeros((ndof, ndof), dtype=float)
    Fint = np.zeros(ndof, dtype=float)
    warnings: list[str] = []
    count = 0
    if state_store is None:
        state_store = {}

    for item in interfaces:
        slave_ids_g = list(item.slave_point_ids)
        master_ids_g = list(item.master_point_ids)
        if len(slave_ids_g) != len(master_ids_g):
            warnings.append(f"Interface '{item.name}' skipped because slave/master point ID counts differ")
            continue
        local_states = state_store.get(item.name, [InterfaceElementState() for _ in slave_ids_g])
        updated_states: list[InterfaceElementState] = []
        for idx, (sg, mg) in enumerate(zip(slave_ids_g, master_ids_g)):
            try:
                ls = submesh.local_by_global[int(sg)]
                lm = submesh.local_by_global[int(mg)]
            except KeyError:
                warnings.append(f"Interface '{item.name}' pair ({sg}, {mg}) skipped because one point is not active")
                continue
            xs = submesh.points[ls]
            xm = submesh.points[lm]
            us = u_nodes[ls]
            um = u_nodes[lm]
            Ki, fi, st = interface_pair_response(xs, xm, us, um, item.parameters, local_states[idx])
            edofs = _edofs_pair(ls, lm)
            K[np.ix_(edofs, edofs)] += Ki
            Fint[edofs] += fi
            updated_states.append(st)
            count += 1
        state_store[item.name] = updated_states
    return InterfaceAssemblyResult(K=K, Fint=Fint, count=count, warnings=warnings), state_store
