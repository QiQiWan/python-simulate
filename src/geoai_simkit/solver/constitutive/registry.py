from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from geoai_simkit.materials.registry import registry as material_registry


@dataclass(slots=True)
class ConstitutiveModelDescriptor:
    name: str
    model_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConstitutiveKernelRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., Any]] = {}

    def register(self, key: str, factory: Callable[..., Any]) -> None:
        self._factories[str(key)] = factory

    def create(self, descriptor: ConstitutiveModelDescriptor):
        if descriptor.model_type in self._factories:
            return self._factories[descriptor.model_type](**descriptor.parameters)
        return material_registry.create(descriptor.model_type, **descriptor.parameters)

    def available(self) -> list[str]:
        return sorted({*self._factories.keys(), *material_registry.available()})
