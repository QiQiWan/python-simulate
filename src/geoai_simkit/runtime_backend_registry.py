from __future__ import annotations

"""Default runtime compiler backend registry."""

from geoai_simkit.adapters.runtime_adapters import DefaultRuntimeCompilerBackend
from geoai_simkit.contracts import RuntimeCompileRequest, RuntimeCompilerBackend
from geoai_simkit.contracts.registry import PluginRegistry

_DEFAULT_REGISTRY: PluginRegistry[RuntimeCompilerBackend] | None = None


def get_default_runtime_compiler_registry() -> PluginRegistry[RuntimeCompilerBackend]:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry: PluginRegistry[RuntimeCompilerBackend] = PluginRegistry(category="runtime_compiler")
        registry.register(DefaultRuntimeCompilerBackend())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_runtime_compiler_backend(backend: RuntimeCompilerBackend, *, replace: bool = False) -> None:
    get_default_runtime_compiler_registry().register(backend, replace=replace)


def resolve_runtime_compiler_backend(request: RuntimeCompileRequest, preferred: str = "auto") -> RuntimeCompilerBackend:
    registry = get_default_runtime_compiler_registry()
    if preferred and preferred != "auto" and preferred in registry:
        return registry.get(preferred)
    return registry.values()[0]


def runtime_compiler_descriptors() -> list[dict[str, object]]:
    return get_default_runtime_compiler_registry().descriptors()


__all__ = [
    "get_default_runtime_compiler_registry",
    "register_runtime_compiler_backend",
    "resolve_runtime_compiler_backend",
    "runtime_compiler_descriptors",
]
