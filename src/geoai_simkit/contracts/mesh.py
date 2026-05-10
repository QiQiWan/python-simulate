from __future__ import annotations

"""Mesh generation contracts."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from .project import ProjectReadPort, project_document_from


@dataclass(frozen=True, slots=True)
class MeshRequest:
    project: ProjectReadPort | object
    mesh_kind: str = "auto"
    options: Mapping[str, object] = field(default_factory=dict)
    attach: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def project_document(self) -> object:
        return project_document_from(self.project)


@dataclass(slots=True)
class MeshResult:
    mesh: object
    mesh_kind: str
    attached: bool = True
    quality: object = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(getattr(self.mesh, "cell_count", 0) or self.metadata.get("allow_empty", False)) and not any(
            str(item).lower().startswith("error") for item in self.warnings
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "mesh_kind": self.mesh_kind,
            "attached": bool(self.attached),
            "node_count": int(getattr(self.mesh, "node_count", 0) or 0),
            "cell_count": int(getattr(self.mesh, "cell_count", 0) or 0),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


SOLID_CELL_TYPES: tuple[str, ...] = ("tet4", "tet4_preview", "tet10", "hex8", "hex8_preview", "hex20", "wedge6", "pyramid5")
SURFACE_CELL_TYPES: tuple[str, ...] = ("tri3", "quad4", "line2")


@dataclass(frozen=True, slots=True)
class SolidAnalysisReadinessIssue:
    """One readiness diagnostic for 3D solid mechanics analysis."""

    severity: str
    code: str
    message: str
    target: str = ""
    hint: str = ""
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
            "hint": self.hint,
            "blocking": self.blocking,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SolidAnalysisReadinessReport:
    """Readiness gate for 3D solid FEM analysis."""

    ready: bool
    mesh_role: str = "unknown"
    mesh_dimension: int = 0
    node_count: int = 0
    cell_count: int = 0
    solid_cell_count: int = 0
    surface_cell_count: int = 0
    cell_families: tuple[str, ...] = ()
    issues: tuple[SolidAnalysisReadinessIssue, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> tuple[SolidAnalysisReadinessIssue, ...]:
        return tuple(issue for issue in self.issues if issue.blocking)

    @property
    def warnings(self) -> tuple[SolidAnalysisReadinessIssue, ...]:
        return tuple(issue for issue in self.issues if not issue.blocking)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": bool(self.ready),
            "mesh_role": self.mesh_role,
            "mesh_dimension": int(self.mesh_dimension),
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "solid_cell_count": int(self.solid_cell_count),
            "surface_cell_count": int(self.surface_cell_count),
            "cell_families": list(self.cell_families),
            "blocking_issues": [issue.to_dict() for issue in self.blocking_issues],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class MeshGenerator(Protocol):
    key: str
    label: str
    supported_mesh_kinds: tuple[str, ...]

    def can_generate(self, request: MeshRequest) -> bool:
        ...

    def generate(self, request: MeshRequest) -> MeshResult:
        ...


class MeshGeneratorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, MeshGenerator] = {}

    def register(self, generator: MeshGenerator, *, replace: bool = False) -> None:
        key = str(generator.key)
        if key in self._items and not replace:
            raise KeyError(f"Mesh generator already registered: {key}")
        self._items[key] = generator

    def get(self, key: str) -> MeshGenerator:
        try:
            return self._items[str(key)]
        except KeyError as exc:
            known = ", ".join(sorted(self._items)) or "<none>"
            raise KeyError(f"Unknown mesh generator {key!r}. Known generators: {known}") from exc

    def resolve(self, request: MeshRequest) -> MeshGenerator:
        preferred = str(request.mesh_kind or "auto")
        if preferred in self._items:
            item = self._items[preferred]
            if item.can_generate(request):
                return item
        for item in self._items.values():
            if item.can_generate(request):
                return item
        known = ", ".join(sorted(self._items)) or "<none>"
        raise KeyError(f"No mesh generator can handle mesh_kind={request.mesh_kind!r}. Registered: {known}")

    def keys(self) -> list[str]:
        return sorted(self._items)

    def descriptors(self) -> list[dict[str, object]]:
        from .registry import describe_plugin

        return [describe_plugin(self._items[key], category="mesh_generator") for key in self.keys()]


__all__ = ["MeshGenerator", "MeshGeneratorRegistry", "MeshRequest", "MeshResult", "SOLID_CELL_TYPES", "SURFACE_CELL_TYPES", "SolidAnalysisReadinessIssue", "SolidAnalysisReadinessReport"]
