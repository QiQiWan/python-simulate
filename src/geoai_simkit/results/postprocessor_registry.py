from __future__ import annotations

"""Default result postprocessor plugin registry."""

from geoai_simkit.adapters.results_adapters import (
    ProjectResultSummaryPostProcessor,
    ResultDatabasePostProcessor,
    ResultPackagePostProcessor,
)
from geoai_simkit.contracts import PostProcessor, ResultRequest
from geoai_simkit.contracts.registry import PluginRegistry

_DEFAULT_REGISTRY: PluginRegistry[PostProcessor] | None = None


def get_default_postprocessor_registry() -> PluginRegistry[PostProcessor]:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry: PluginRegistry[PostProcessor] = PluginRegistry(category="postprocessor")
        registry.register(ProjectResultSummaryPostProcessor())
        registry.register(ResultDatabasePostProcessor())
        registry.register(ResultPackagePostProcessor())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_postprocessor(processor: PostProcessor, *, replace: bool = False) -> None:
    get_default_postprocessor_registry().register(processor, replace=replace)


def resolve_postprocessor(request: ResultRequest, preferred: str = "auto") -> PostProcessor:
    registry = get_default_postprocessor_registry()
    if preferred and preferred != "auto" and preferred in registry:
        return registry.get(preferred)
    source = request.source_document()
    if hasattr(source, "result_store"):
        return registry.get("project_result_summary")
    if hasattr(source, "stage_names") and hasattr(source, "fields"):
        return registry.get("result_database_summary")
    if hasattr(source, "stage_metrics") or hasattr(source, "stage_records") or hasattr(source, "add_stage_metric"):
        return registry.get("result_package_summary")
    return registry.values()[0]


def postprocessor_descriptors() -> list[dict[str, object]]:
    return get_default_postprocessor_registry().descriptors()


__all__ = [
    "get_default_postprocessor_registry",
    "postprocessor_descriptors",
    "register_postprocessor",
    "resolve_postprocessor",
]
