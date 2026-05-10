from __future__ import annotations

"""Dependency-light contact and structural-interface solver contracts.

The DTOs here are intentionally independent from the project document and FEM
implementation so services, GUI controllers and reporting code can inspect
contact/interface results without importing solver internals.
"""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ContactMaterialParameters:
    material_id: str = ""
    kn: float = 1.0e6
    ks: float = 5.0e5
    friction_deg: float = 25.0
    cohesion: float = 0.0
    tensile_cutoff: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "material_id": self.material_id,
            "kn": float(self.kn),
            "ks": float(self.ks),
            "friction_deg": float(self.friction_deg),
            "cohesion": float(self.cohesion),
            "tensile_cutoff": float(self.tensile_cutoff),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class InterfaceKinematics:
    interface_id: str
    normal_gap: float = 0.0
    tangential_slip: tuple[float, float] = (0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def tangential_slip_norm(self) -> float:
        return float((self.tangential_slip[0] ** 2 + self.tangential_slip[1] ** 2) ** 0.5)

    def to_dict(self) -> dict[str, object]:
        return {
            "interface_id": self.interface_id,
            "normal_gap": float(self.normal_gap),
            "tangential_slip": [float(v) for v in self.tangential_slip],
            "tangential_slip_norm": self.tangential_slip_norm,
            "normal": [float(v) for v in self.normal],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ContactPairState:
    interface_id: str
    status: str
    normal_gap: float = 0.0
    tangential_slip: tuple[float, float] = (0.0, 0.0)
    normal_traction: float = 0.0
    shear_traction: tuple[float, float] = (0.0, 0.0)
    friction_limit: float = 0.0
    slip_multiplier: float = 0.0
    active: bool = False
    material_id: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def shear_traction_norm(self) -> float:
        return float((self.shear_traction[0] ** 2 + self.shear_traction[1] ** 2) ** 0.5)

    def to_dict(self) -> dict[str, object]:
        return {
            "interface_id": self.interface_id,
            "status": self.status,
            "normal_gap": float(self.normal_gap),
            "tangential_slip": [float(v) for v in self.tangential_slip],
            "normal_traction": float(self.normal_traction),
            "shear_traction": [float(v) for v in self.shear_traction],
            "shear_traction_norm": self.shear_traction_norm,
            "friction_limit": float(self.friction_limit),
            "slip_multiplier": float(self.slip_multiplier),
            "active": bool(self.active),
            "material_id": self.material_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ContactIterationReport:
    iteration: int
    active_count: int
    stick_count: int
    slip_count: int
    open_count: int
    active_set_changed: bool = False
    residual_norm: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "iteration": int(self.iteration),
            "active_count": int(self.active_count),
            "stick_count": int(self.stick_count),
            "slip_count": int(self.slip_count),
            "open_count": int(self.open_count),
            "active_set_changed": bool(self.active_set_changed),
            "residual_norm": float(self.residual_norm),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ContactSolverReport:
    ok: bool
    status: str
    algorithm: str = "coulomb_penalty_contact_v1"
    pair_states: tuple[ContactPairState, ...] = ()
    iterations: tuple[ContactIterationReport, ...] = ()
    active_set_converged: bool = True
    committed_state: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def interface_count(self) -> int:
        return len(self.pair_states)

    @property
    def active_count(self) -> int:
        return sum(1 for row in self.pair_states if row.active)

    @property
    def slip_count(self) -> int:
        return sum(1 for row in self.pair_states if row.status == "slip")

    @property
    def open_count(self) -> int:
        return sum(1 for row in self.pair_states if row.status == "open")

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "status": self.status,
            "algorithm": self.algorithm,
            "interface_count": self.interface_count,
            "active_count": self.active_count,
            "slip_count": self.slip_count,
            "open_count": self.open_count,
            "active_set_converged": bool(self.active_set_converged),
            "committed_state": bool(self.committed_state),
            "pair_states": [row.to_dict() for row in self.pair_states],
            "iterations": [row.to_dict() for row in self.iterations],
            "metadata": dict(self.metadata),
        }


__all__ = [
    "ContactIterationReport",
    "ContactMaterialParameters",
    "ContactPairState",
    "ContactSolverReport",
    "InterfaceKinematics",
]
