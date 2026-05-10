from __future__ import annotations

"""Material model provider adapters."""

from geoai_simkit.contracts import PluginCapability, PluginHealth
from geoai_simkit.contracts.material import MaterialModelRequest, MaterialModelResult


class BuiltinMaterialModelProvider:
    key = "builtin_material_models"
    label = "Built-in material model registry"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="material_model_provider",
        version="1",
        features=("linear_elastic", "mohr_coulomb", "hss", "registry_factory"),
        supported_inputs=("MaterialModelRequest",),
        supported_outputs=("MaterialModel",),
        health=PluginHealth(available=True),
    )

    def supported_model_keys(self) -> tuple[str, ...]:
        from geoai_simkit.materials.registry import registry

        return tuple(registry.available())

    def can_create(self, request: MaterialModelRequest) -> bool:
        return str(request.model_key) in self.supported_model_keys() or ":" in str(request.model_key)

    def create_model(self, request: MaterialModelRequest) -> MaterialModelResult:
        from geoai_simkit.materials.registry import registry

        model = registry.create(str(request.model_key), **dict(request.parameters))
        return MaterialModelResult(
            model_key=str(request.model_key),
            model=model,
            metadata={"provider": self.key, **dict(request.metadata)},
        )


__all__ = ["BuiltinMaterialModelProvider"]
