from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.core.model import SimulationModel


@dataclass(slots=True)
class SolverSettings:
    analysis_type: str = "static"
    backend: str = "warp"
    max_steps: int = 100
    max_iterations: int = 12
    tolerance: float = 1e-5
    dt: float = 1e-2
    device: str = "auto"
    thread_count: int = 0
    gravity: tuple[float, float, float] = (0.0, 0.0, -9.81)
    displacement_scale: float = 1.0
    prefer_sparse: bool = True
    line_search: bool = True
    max_cutbacks: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.max_steps = int(max(1, self.max_steps))
        self.max_iterations = int(max(1, self.max_iterations))
        if "max_nonlinear_iterations" not in self.metadata:
            self.metadata["max_nonlinear_iterations"] = int(self.max_iterations)
        self.thread_count = int(max(0, getattr(self, 'thread_count', 0)))


class SolverBackend(ABC):
    @abstractmethod
    def solve(self, model: SimulationModel, settings: SolverSettings) -> SimulationModel:
        raise NotImplementedError
