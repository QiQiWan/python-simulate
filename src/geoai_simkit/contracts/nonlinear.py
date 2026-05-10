from __future__ import annotations

"""Dependency-light nonlinear solver core contracts.

The DTOs in this module are intentionally independent of project/solver
implementations so GUI, workflow and reporting layers can inspect nonlinear
runs without importing the nonlinear solver internals.
"""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class LoadIncrement:
    index: int
    target_load_factor: float
    actual_load_factor: float
    cutback_level: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "index": int(self.index),
            "target_load_factor": float(self.target_load_factor),
            "actual_load_factor": float(self.actual_load_factor),
            "cutback_level": int(self.cutback_level),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NewtonIterationReport:
    increment: int
    iteration: int
    residual_norm: float
    displacement_norm: float = 0.0
    energy_norm: float = 0.0
    converged: bool = False
    tangent: str = "elastic_predictor_secant"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "increment": int(self.increment),
            "iteration": int(self.iteration),
            "residual_norm": float(self.residual_norm),
            "displacement_norm": float(self.displacement_norm),
            "energy_norm": float(self.energy_norm),
            "converged": bool(self.converged),
            "tangent": self.tangent,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PlasticStateSnapshot:
    stress: tuple[float, ...] = ()
    strain: tuple[float, ...] = ()
    plastic_strain: tuple[float, ...] = ()
    yielded: bool = False
    yield_mode: str = "elastic"
    yield_margin: float = 0.0
    plastic_multiplier: float = 0.0
    equivalent_plastic_strain: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "stress": [float(v) for v in self.stress],
            "strain": [float(v) for v in self.strain],
            "plastic_strain": [float(v) for v in self.plastic_strain],
            "yielded": bool(self.yielded),
            "yield_mode": self.yield_mode,
            "yield_margin": float(self.yield_margin),
            "plastic_multiplier": float(self.plastic_multiplier),
            "equivalent_plastic_strain": float(self.equivalent_plastic_strain),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ReturnMappingResult:
    accepted: bool
    status: str
    material_model: str
    initial_state: PlasticStateSnapshot
    final_state: PlasticStateSnapshot
    strain_increment: tuple[float, ...]
    algorithm: str = "mohr_coulomb_return_mapping_v1"
    iteration_count: int = 1
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    @property
    def yielded(self) -> bool:
        return bool(self.final_state.yielded)

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": bool(self.accepted),
            "status": self.status,
            "material_model": self.material_model,
            "algorithm": self.algorithm,
            "iteration_count": int(self.iteration_count),
            "yielded": self.yielded,
            "initial_state": self.initial_state.to_dict(),
            "final_state": self.final_state.to_dict(),
            "strain_increment": [float(v) for v in self.strain_increment],
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True, slots=True)
class CutbackRecord:
    increment: int
    attempt: int
    previous_load_factor: float
    new_load_factor: float
    reason: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "increment": int(self.increment),
            "attempt": int(self.attempt),
            "previous_load_factor": float(self.previous_load_factor),
            "new_load_factor": float(self.new_load_factor),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class NonlinearSolverCoreReport:
    ok: bool
    status: str
    algorithm: str = "nonlinear_solver_core_v1"
    load_increments: tuple[LoadIncrement, ...] = ()
    iterations: tuple[NewtonIterationReport, ...] = ()
    return_mapping_results: tuple[ReturnMappingResult, ...] = ()
    cutbacks: tuple[CutbackRecord, ...] = ()
    committed_state: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def increment_count(self) -> int:
        return len(self.load_increments)

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    @property
    def yielded_count(self) -> int:
        return sum(1 for row in self.return_mapping_results if row.yielded)

    @property
    def yielded_fraction(self) -> float:
        total = len(self.return_mapping_results)
        return float(self.yielded_count / total) if total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "status": self.status,
            "algorithm": self.algorithm,
            "increment_count": self.increment_count,
            "iteration_count": self.iteration_count,
            "yielded_count": self.yielded_count,
            "yielded_fraction": self.yielded_fraction,
            "committed_state": bool(self.committed_state),
            "load_increments": [row.to_dict() for row in self.load_increments],
            "iterations": [row.to_dict() for row in self.iterations],
            "return_mapping_results": [row.to_dict() for row in self.return_mapping_results],
            "cutbacks": [row.to_dict() for row in self.cutbacks],
            "metadata": dict(self.metadata),
        }


__all__ = [
    "CutbackRecord",
    "LoadIncrement",
    "NewtonIterationReport",
    "NonlinearSolverCoreReport",
    "PlasticStateSnapshot",
    "ReturnMappingResult",
]
