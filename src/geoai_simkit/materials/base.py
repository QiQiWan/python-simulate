from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class MaterialState:
    stress: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=float))
    strain: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=float))
    plastic_strain: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=float))
    internal: dict[str, Any] = field(default_factory=dict)


class MaterialModel(ABC):
    name: str = "material"

    @abstractmethod
    def create_state(self) -> MaterialState:
        raise NotImplementedError

    @abstractmethod
    def update(self, dstrain: np.ndarray, state: MaterialState) -> MaterialState:
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    def validate_parameters(self) -> None:
        return None

    def state_layout(self) -> tuple[str, ...]:
        return tuple(self.create_state().internal.keys())

    def tangent_matrix(self, state: MaterialState | None = None) -> np.ndarray:
        raise NotImplementedError(f"{type(self).__name__} does not provide a tangent matrix")
