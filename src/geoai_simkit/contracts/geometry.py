from __future__ import annotations

"""Geometry/modeling contracts."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GeometryBuildRequest:
    project: object
    operation: str = "build"
    parameters: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class GeometryBuildResult:
    project: object
    geometry: object = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "warnings": list(self.warnings), "metadata": dict(self.metadata)}


@runtime_checkable
class GeometryBuilder(Protocol):
    key: str

    def build(self, request: GeometryBuildRequest) -> GeometryBuildResult:
        ...


__all__ = ["GeometryBuildRequest", "GeometryBuildResult", "GeometryBuilder"]
