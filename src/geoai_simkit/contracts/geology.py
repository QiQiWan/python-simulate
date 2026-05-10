from __future__ import annotations

"""Geology/import contracts."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GeologySource:
    source: str | Path | Mapping[str, object]
    source_type: str | None = None
    options: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source) if isinstance(self.source, Path) else self.source,
            "source_type": self.source_type,
            "options": dict(self.options),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GeologyImportPayload:
    project: object
    source_type: str
    diagnostics: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(str(item).lower().startswith("error") for item in self.diagnostics)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "source_type": self.source_type,
            "diagnostics": list(self.diagnostics),
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class GeologyImporter(Protocol):
    key: str
    label: str
    supported_source_types: tuple[str, ...]

    def can_import(self, source: GeologySource) -> bool:
        ...

    def import_source(self, source: GeologySource) -> GeologyImportPayload:
        ...


__all__ = ["GeologyImportPayload", "GeologyImporter", "GeologySource"]
