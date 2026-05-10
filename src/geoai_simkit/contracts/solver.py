from __future__ import annotations

"""Solver backend contracts and registry."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from .project import ProjectReadPort, project_document_from


@dataclass(frozen=True, slots=True)
class SolverCapabilities:
    key: str
    label: str
    devices: tuple[str, ...] = ("cpu",)
    stage_solve: bool = True
    nonlinear: bool = False
    gpu: bool = False
    deterministic: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "devices": list(self.devices),
            "stage_solve": bool(self.stage_solve),
            "nonlinear": bool(self.nonlinear),
            "gpu": bool(self.gpu),
            "deterministic": bool(self.deterministic),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SolveRequest:
    model: object = None
    project: ProjectReadPort | object = None
    stage_ids: tuple[str, ...] = ()
    settings: object = None
    compile_if_needed: bool = True
    write_results: bool = True
    backend_preference: str = "reference_cpu"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def target(self) -> object:
        target = self.project if self.project is not None else self.model
        return project_document_from(target)


@dataclass(slots=True)
class SolveResult:
    accepted: bool
    status: str = "unknown"
    backend_key: str = "unknown"
    solved_model: object = None
    result_store: object = None
    summary: object = None
    phase_records: tuple[object, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.accepted) and str(self.status).lower() not in {"error", "failed", "rejected"}

    def to_dict(self) -> dict[str, object]:
        records = []
        for row in self.phase_records:
            if hasattr(row, "to_dict"):
                records.append(row.to_dict())
            elif isinstance(row, Mapping):
                records.append(dict(row))
            else:
                records.append({"value": str(row)})
        return {
            "ok": self.ok,
            "accepted": bool(self.accepted),
            "status": self.status,
            "backend_key": self.backend_key,
            "phase_records": records,
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class SolverBackend(Protocol):
    key: str
    capabilities: SolverCapabilities

    def can_solve(self, request: SolveRequest) -> bool:
        ...

    def solve(self, request: SolveRequest) -> SolveResult:
        ...


class SolverBackendRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SolverBackend] = {}

    def register(self, backend: SolverBackend, *, replace: bool = False) -> None:
        key = str(backend.key)
        if key in self._items and not replace:
            raise KeyError(f"Solver backend already registered: {key}")
        self._items[key] = backend

    def get(self, key: str) -> SolverBackend:
        try:
            return self._items[str(key)]
        except KeyError as exc:
            known = ", ".join(sorted(self._items)) or "<none>"
            raise KeyError(f"Unknown solver backend {key!r}. Known backends: {known}") from exc

    def resolve(self, request: SolveRequest) -> SolverBackend:
        preferred = str(request.backend_preference or "")
        if preferred and preferred != "auto" and preferred in self._items:
            item = self._items[preferred]
            if item.can_solve(request):
                return item
        for item in self._items.values():
            if item.can_solve(request):
                return item
        known = ", ".join(sorted(self._items)) or "<none>"
        raise KeyError(f"No solver backend can handle request. Registered: {known}")

    def keys(self) -> list[str]:
        return sorted(self._items)

    def capabilities(self) -> list[dict[str, object]]:
        from .registry import describe_plugin

        rows: list[dict[str, object]] = []
        for key in self.keys():
            item = self._items[key]
            raw = getattr(getattr(item, "capabilities", None), "metadata", {}) or {}
            plugin_capability = raw.get("plugin_capability") if isinstance(raw, Mapping) else None
            if isinstance(plugin_capability, Mapping):
                rows.append({
                    "key": str(plugin_capability.get("key", key)),
                    "label": str(plugin_capability.get("label", key)),
                    "category": str(plugin_capability.get("category", "solver_backend")),
                    "version": str(plugin_capability.get("version", "1")),
                    "available": bool(plugin_capability.get("available", True)),
                    "capabilities": dict(plugin_capability),
                    "health": dict(plugin_capability.get("health", {})),
                    "metadata": dict(plugin_capability.get("metadata", {})),
                })
            else:
                rows.append(describe_plugin(item, category="solver_backend"))
        return rows


__all__ = ["SolveRequest", "SolveResult", "SolverBackend", "SolverBackendRegistry", "SolverCapabilities"]
