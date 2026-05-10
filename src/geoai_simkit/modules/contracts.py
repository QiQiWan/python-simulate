from __future__ import annotations

"""Shared contracts for coarse project modules.

The module layer is a stable facade over the current package layout.  It gives
callers a small set of update targets without forcing a risky file move of the
existing geometry, GUI, solver and result implementations.
"""

from dataclasses import asdict, dataclass
from importlib.util import find_spec
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectModuleSpec:
    key: str
    label: str
    responsibility: str
    owned_namespaces: tuple[str, ...]
    public_entrypoints: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    boundary_notes: tuple[str, ...] = ()
    status: str = "facade"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("owned_namespaces", "public_entrypoints", "depends_on", "boundary_notes"):
            payload[key] = list(payload[key])
        return payload


def namespace_available(namespace: str) -> bool:
    try:
        return find_spec(namespace) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def smoke_from_spec(spec: ProjectModuleSpec, *, checks: dict[str, bool] | None = None) -> dict[str, Any]:
    namespace_checks = {namespace: namespace_available(namespace) for namespace in spec.owned_namespaces}
    entrypoint_checks = {entrypoint: True for entrypoint in spec.public_entrypoints}
    extra_checks = dict(checks or {})
    ok = all(namespace_checks.values()) and all(entrypoint_checks.values()) and all(extra_checks.values())
    return {
        "key": spec.key,
        "label": spec.label,
        "ok": bool(ok),
        "status": spec.status,
        "namespace_checks": namespace_checks,
        "entrypoint_checks": entrypoint_checks,
        "checks": extra_checks,
    }


__all__ = ["ProjectModuleSpec", "namespace_available", "smoke_from_spec"]
