from __future__ import annotations

"""Runtime bundle contracts."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RuntimeCompileRequest:
    prepared_case: object
    compile_config: object = None
    runtime_config: object = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeBundlePayload:
    bundle: object
    manifest: Mapping[str, object] = field(default_factory=dict)
    compile_report: Mapping[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"manifest": dict(self.manifest), "compile_report": dict(self.compile_report), "metadata": dict(self.metadata)}


@runtime_checkable
class RuntimeCompilerBackend(Protocol):
    key: str

    def compile(self, request: RuntimeCompileRequest) -> RuntimeBundlePayload:
        ...


@runtime_checkable
class RuntimeBundleStore(Protocol):
    def write(self, payload: RuntimeBundlePayload, target: str | Path) -> Path:
        ...

    def read_manifest(self, source: str | Path) -> Mapping[str, object]:
        ...


__all__ = ["RuntimeBundlePayload", "RuntimeBundleStore", "RuntimeCompileRequest", "RuntimeCompilerBackend"]
