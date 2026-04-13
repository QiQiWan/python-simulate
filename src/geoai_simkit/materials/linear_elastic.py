from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import MaterialModel, MaterialState
from .registry import registry


@dataclass(slots=True)
class LinearElastic(MaterialModel):
    E: float
    nu: float
    rho: float = 0.0
    name: str = "linear_elastic"

    def validate_parameters(self) -> None:
        if self.E <= 0:
            raise ValueError("E must be positive")
        if not (0.0 <= self.nu < 0.5):
            raise ValueError("nu must be in [0, 0.5)")

    def create_state(self) -> MaterialState:
        return MaterialState()

    def elastic_matrix(self) -> np.ndarray:
        lam = self.E * self.nu / ((1.0 + self.nu) * (1.0 - 2.0 * self.nu))
        mu = self.E / (2.0 * (1.0 + self.nu))
        return np.array([
            [lam + 2 * mu, lam, lam, 0, 0, 0],
            [lam, lam + 2 * mu, lam, 0, 0, 0],
            [lam, lam, lam + 2 * mu, 0, 0, 0],
            [0, 0, 0, mu, 0, 0],
            [0, 0, 0, 0, mu, 0],
            [0, 0, 0, 0, 0, mu],
        ], dtype=float)

    def tangent_matrix(self, state: MaterialState | None = None) -> np.ndarray:
        return self.elastic_matrix()

    def update(self, dstrain: np.ndarray, state: MaterialState) -> MaterialState:
        C = self.elastic_matrix()
        return MaterialState(
            stress=state.stress + C @ dstrain,
            strain=state.strain + dstrain,
            plastic_strain=state.plastic_strain.copy(),
            internal=dict(state.internal),
        )

    def describe(self) -> dict[str, float]:
        return {"E": self.E, "nu": self.nu, "rho": self.rho}


registry.register("linear_elastic", LinearElastic)
