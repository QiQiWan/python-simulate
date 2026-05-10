from __future__ import annotations

"""Default stage-compiler plugin registry."""

from geoai_simkit.adapters.stage_adapters import GeoProjectStageCompilerAdapter
from geoai_simkit.contracts import StageCompileRequest, StageCompiler
from geoai_simkit.contracts.registry import PluginRegistry

_DEFAULT_REGISTRY: PluginRegistry[StageCompiler] | None = None


def get_default_stage_compiler_registry() -> PluginRegistry[StageCompiler]:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry: PluginRegistry[StageCompiler] = PluginRegistry(category="stage_compiler")
        registry.register(GeoProjectStageCompilerAdapter())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_stage_compiler(compiler: StageCompiler, *, replace: bool = False) -> None:
    get_default_stage_compiler_registry().register(compiler, replace=replace)


def resolve_stage_compiler(request: StageCompileRequest, preferred: str = "auto") -> StageCompiler:
    registry = get_default_stage_compiler_registry()
    if preferred and preferred != "auto" and preferred in registry:
        return registry.get(preferred)
    project = request.project
    for compiler in registry.values():
        if getattr(compiler, "key", "") == "geoproject_phase_compiler" and hasattr(project, "compile_phase_models"):
            return compiler
    return registry.values()[0]


def stage_compiler_descriptors() -> list[dict[str, object]]:
    return get_default_stage_compiler_registry().descriptors()


__all__ = [
    "get_default_stage_compiler_registry",
    "register_stage_compiler",
    "resolve_stage_compiler",
    "stage_compiler_descriptors",
]
