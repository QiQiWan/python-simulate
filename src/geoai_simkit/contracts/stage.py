from __future__ import annotations

"""Stage-planning contracts."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from .project import ProjectReadPort, project_document_from


@dataclass(frozen=True, slots=True)
class StageCompileRequest:
    project: ProjectReadPort | object
    stage_ids: tuple[str, ...] = ()
    options: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def project_document(self) -> object:
        return project_document_from(self.project)


@dataclass(slots=True)
class StageCompileResult:
    phase_models: object
    stage_count: int
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.stage_count >= 0 and not any(str(item).lower().startswith("error") for item in self.warnings)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "stage_count": int(self.stage_count), "warnings": list(self.warnings), "metadata": dict(self.metadata)}


@runtime_checkable
class StageCompiler(Protocol):
    key: str

    def compile(self, request: StageCompileRequest) -> StageCompileResult:
        ...


__all__ = ["StageCompileRequest", "StageCompileResult", "StageCompiler"]
