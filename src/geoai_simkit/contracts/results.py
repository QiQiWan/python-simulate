from __future__ import annotations

"""Result and postprocessing contracts."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from .project import project_document_from


@dataclass(frozen=True, slots=True)
class ResultRequest:
    source: object
    stage_ids: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def source_document(self) -> object:
        return project_document_from(self.source)


@dataclass(slots=True)
class ResultSummary:
    stage_count: int = 0
    field_count: int = 0
    accepted: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_count": int(self.stage_count),
            "field_count": int(self.field_count),
            "accepted": bool(self.accepted),
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class ResultSink(Protocol):
    key: str

    def write(self, result: object, *, metadata: Mapping[str, object] | None = None) -> ResultSummary:
        ...


@runtime_checkable
class PostProcessor(Protocol):
    key: str

    def summarize(self, request: ResultRequest) -> ResultSummary:
        ...


__all__ = ["PostProcessor", "ResultRequest", "ResultSink", "ResultSummary"]
