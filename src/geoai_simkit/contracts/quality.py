from __future__ import annotations

"""Quality gate contracts for verified 3D geotechnical workflows."""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class QualityGateIssue:
    severity: str
    code: str
    message: str
    target: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return str(self.severity).lower() in {"error", "blocking"}

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "blocking": self.blocking,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ElementQualityMetric:
    cell_id: int
    cell_type: str
    volume: float | None = None
    aspect_ratio: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": int(self.cell_id),
            "cell_type": self.cell_type,
            "volume": self.volume,
            "aspect_ratio": self.aspect_ratio,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MeshQualityGateReport:
    ok: bool
    checked_cell_count: int = 0
    solid_cell_count: int = 0
    min_volume: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_ids: tuple[int, ...] = ()
    issues: tuple[QualityGateIssue, ...] = ()
    metrics: tuple[ElementQualityMetric, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> tuple[QualityGateIssue, ...]:
        return tuple(item for item in self.issues if item.blocking)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "checked_cell_count": int(self.checked_cell_count),
            "solid_cell_count": int(self.solid_cell_count),
            "min_volume": self.min_volume,
            "max_aspect_ratio": self.max_aspect_ratio,
            "bad_cell_ids": list(self.bad_cell_ids),
            "blocking_issues": [item.to_dict() for item in self.blocking_issues],
            "issues": [item.to_dict() for item in self.issues],
            "metrics": [item.to_dict() for item in self.metrics],
            "metadata": {"contract": "mesh_quality_gate_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class MaterialCompatibilityReport:
    ok: bool
    solver_backend: str
    material_ids: tuple[str, ...] = ()
    missing_material_ids: tuple[str, ...] = ()
    incompatible_material_ids: tuple[str, ...] = ()
    issues: tuple[QualityGateIssue, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> tuple[QualityGateIssue, ...]:
        return tuple(item for item in self.issues if item.blocking)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "solver_backend": self.solver_backend,
            "material_ids": list(self.material_ids),
            "missing_material_ids": list(self.missing_material_ids),
            "incompatible_material_ids": list(self.incompatible_material_ids),
            "blocking_issues": [item.to_dict() for item in self.blocking_issues],
            "issues": [item.to_dict() for item in self.issues],
            "metadata": {"contract": "material_compatibility_gate_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class GeotechnicalQualityGateReport:
    ok: bool
    mesh_quality: MeshQualityGateReport
    material_compatibility: MaterialCompatibilityReport
    readiness: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "mesh_quality": self.mesh_quality.to_dict(),
            "material_compatibility": self.material_compatibility.to_dict(),
            "readiness": dict(self.readiness),
            "metadata": {"contract": "geotechnical_quality_gate_v1", **dict(self.metadata)},
        }


__all__ = [
    "ElementQualityMetric",
    "GeotechnicalQualityGateReport",
    "MaterialCompatibilityReport",
    "MeshQualityGateReport",
    "QualityGateIssue",
]
