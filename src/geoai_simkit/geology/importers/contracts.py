from __future__ import annotations

"""Contracts shared by geological model importers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


def normalize_source_type(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


@dataclass(slots=True)
class GeologyImportDiagnostic:
    severity: str
    code: str
    message: str
    target: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GeologyImportRequest:
    source: str | Path | Mapping[str, Any]
    source_type: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_source_type(self) -> str:
        explicit = normalize_source_type(self.source_type)
        if explicit:
            return explicit
        if isinstance(self.source, Mapping):
            for key in ("source_type", "kind", "format", "contract"):
                value = normalize_source_type(str(self.source.get(key, "")))
                if value:
                    return value
            return "geology_json"
        suffix = Path(self.source).suffix.lower().lstrip(".")
        if suffix == "stl":
            return "stl_geology"
        if suffix in {"json", "geojson"}:
            return "geology_json"
        if suffix == "csv":
            return "borehole_csv"
        return suffix

    @property
    def source_path(self) -> Path | None:
        if isinstance(self.source, Mapping):
            return None
        return Path(self.source)


@dataclass(slots=True)
class GeologyImportResult:
    source_type: str
    project: Any
    diagnostics: list[GeologyImportDiagnostic] = field(default_factory=list)
    source_path: str | None = None
    imported_object_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(row.severity == "error" for row in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "imported_object_count": int(self.imported_object_count),
            "diagnostics": [row.to_dict() for row in self.diagnostics],
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class GeologyImporter(Protocol):
    label: str
    source_types: tuple[str, ...]

    def can_import(self, request: GeologyImportRequest) -> bool:
        ...

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        ...


__all__ = [
    "GeologyImportDiagnostic",
    "GeologyImportRequest",
    "GeologyImportResult",
    "GeologyImporter",
    "normalize_source_type",
]
