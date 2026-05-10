from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class InterfaceMaterialState:
    normal_gap: float = 0.0
    normal_traction: float = 0.0
    tangential_traction: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    plastic_slip: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    status: str = 'open'
    internal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'normal_gap': float(self.normal_gap),
            'normal_traction': float(self.normal_traction),
            'tangential_traction': [float(v) for v in np.asarray(self.tangential_traction, dtype=float).reshape(3)],
            'plastic_slip': [float(v) for v in np.asarray(self.plastic_slip, dtype=float).reshape(3)],
            'status': self.status,
            'internal': dict(self.internal),
        }


@dataclass(frozen=True, slots=True)
class CoulombInterfaceMaterial:
    """Small-strain zero-thickness Coulomb interface law.

    The sign convention is gap > 0 for separation, gap < 0 for penetration.
    The returned normal traction is compressive positive and projected onto the
    Kuhn-Tucker conditions ``g_n >= 0, lambda_n >= 0, g_n*lambda_n = 0`` in the
    active-set sense used by the global solver.
    """

    kn: float = 5.0e8
    ks: float = 1.0e8
    friction_deg: float = 25.0
    cohesion: float = 0.0
    tensile_cutoff: float = 0.0
    regularization: float = 1.0e-12

    @property
    def mu(self) -> float:
        return float(np.tan(np.deg2rad(float(self.friction_deg))))

    def update(
        self,
        jump: np.ndarray,
        normal: np.ndarray,
        state: InterfaceMaterialState | None = None,
        *,
        gap_tolerance: float = 1.0e-9,
    ) -> tuple[InterfaceMaterialState, np.ndarray, np.ndarray, dict[str, Any]]:
        n = np.asarray(normal, dtype=float).reshape(3)
        nrm = float(np.linalg.norm(n))
        if nrm <= 1.0e-14:
            n = np.array([0.0, 0.0, 1.0], dtype=float)
        else:
            n = n / nrm
        du = np.asarray(jump, dtype=float).reshape(3)
        gap = float(np.dot(du, n))
        Pn = np.outer(n, n)
        Pt = np.eye(3, dtype=float) - Pn
        tangential_jump = Pt @ du
        trial_t = float(self.ks) * tangential_jump
        tnorm = float(np.linalg.norm(trial_t))
        penetration = max(0.0, -gap)
        lambda_n = max(0.0, float(self.kn) * penetration - float(self.tensile_cutoff))
        limit = max(0.0, float(self.cohesion) + self.mu * lambda_n)
        status = 'open'
        traction = np.zeros(3, dtype=float)
        tangent = np.zeros((3, 3), dtype=float)
        slip = np.zeros(3, dtype=float) if state is None else np.asarray(state.plastic_slip, dtype=float).reshape(3).copy()
        slip_increment = np.zeros(3, dtype=float)
        friction_violation = max(0.0, tnorm - limit)
        if gap <= float(gap_tolerance) or lambda_n > 0.0:
            tangent += float(self.kn) * Pn
            normal_force = -lambda_n * n
            if tnorm <= limit + float(self.regularization):
                shear = trial_t
                tangent += float(self.ks) * Pt
                status = 'stick'
            else:
                scale = limit / max(tnorm, float(self.regularization))
                shear = scale * trial_t
                # Algorithmic slip tangent: keep the orthogonal part and remove
                # the over-stiff direction of sliding to avoid artificial shear locking.
                tdir = trial_t / max(tnorm, float(self.regularization))
                tangent += float(self.ks) * scale * (Pt - np.outer(tdir, tdir))
                slip_increment = (1.0 - scale) * tangential_jump
                slip += slip_increment
                status = 'slip'
            traction = normal_force + shear
        comp = {
            'gap': float(gap),
            'lambda_n': float(lambda_n),
            'gap_positive_violation': float(max(0.0, -gap) if lambda_n <= 0.0 else 0.0),
            'normal_tension_violation': float(max(0.0, -lambda_n)),
            'normal_complementarity': float(abs(max(gap, 0.0) * lambda_n)),
            'tangential_trial_norm': float(tnorm),
            'friction_limit': float(limit),
            'friction_violation': float(friction_violation),
            'status': status,
            'mu': float(self.mu),
        }
        out_state = InterfaceMaterialState(
            normal_gap=float(gap),
            normal_traction=float(lambda_n),
            tangential_traction=np.asarray(traction - np.dot(traction, n) * n, dtype=float),
            plastic_slip=slip,
            status=status,
            internal={'slip_increment_norm': float(np.linalg.norm(slip_increment)), **comp},
        )
        return out_state, traction, tangent, comp


__all__ = ['CoulombInterfaceMaterial', 'InterfaceMaterialState']
