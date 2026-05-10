from __future__ import annotations

"""Default material model provider registry."""

from geoai_simkit.adapters.material_adapters import BuiltinMaterialModelProvider
from geoai_simkit.contracts.material import (
    MaterialModelProvider,
    MaterialModelProviderRegistry,
    MaterialModelRequest,
    MaterialModelResult,
)

_DEFAULT_REGISTRY: MaterialModelProviderRegistry | None = None


def get_default_material_model_registry() -> MaterialModelProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = MaterialModelProviderRegistry()
        registry.register(BuiltinMaterialModelProvider())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def register_material_model_provider(provider: MaterialModelProvider, *, replace: bool = False) -> None:
    get_default_material_model_registry().register(provider, replace=replace)


def create_material_model(
    model_key: str,
    *,
    parameters: dict[str, object] | None = None,
    provider: str = "auto",
    metadata: dict[str, object] | None = None,
) -> MaterialModelResult:
    request = MaterialModelRequest(
        model_key=str(model_key),
        parameters=dict(parameters or {}),
        metadata=dict(metadata or {}),
    )
    return get_default_material_model_registry().resolve(request, preferred=provider).create_model(request)


def material_model_provider_descriptors() -> list[dict[str, object]]:
    return get_default_material_model_registry().descriptors()


__all__ = [
    "create_material_model",
    "get_default_material_model_registry",
    "material_model_provider_descriptors",
    "register_material_model_provider",
]
