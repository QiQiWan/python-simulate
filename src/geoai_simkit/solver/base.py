from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SolverSettings:
    """Common solver settings used by local and benchmark solvers."""

    backend: str = "reference_cpu"
    result_mode: str = "strict"
    max_iterations: int = 20
    tolerance: float = 1.0e-8
    line_search: bool = True
    prefer_sparse: bool = True
    max_cutbacks: int = 0
    device: str = "cpu"
    thread_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def strict(self) -> bool:
        return str(self.result_mode).lower() == "strict"


@dataclass(slots=True)
class SolverResult:
    converged: bool
    displacement: Any = None
    residual_norm: float = 0.0
    iterations: int = 0
    status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
