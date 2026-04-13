from __future__ import annotations

import importlib
from collections.abc import Callable

from .base import MaterialModel


class MaterialRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., MaterialModel]] = {}

    def register(self, key: str, factory: Callable[..., MaterialModel]) -> None:
        self._factories[key] = factory

    def create(self, key: str, **kwargs) -> MaterialModel:
        if key in self._factories:
            model = self._factories[key](**kwargs)
            model.validate_parameters()
            return model
        if ":" in key:
            module_name, symbol = key.split(":", 1)
            mod = importlib.import_module(module_name)
            factory = getattr(mod, symbol)
            model = factory(**kwargs)
            if not isinstance(model, MaterialModel):
                raise TypeError(f"Dynamic material '{key}' did not return a MaterialModel")
            model.validate_parameters()
            return model
        raise KeyError(f"Unknown material model: {key}")

    def available(self) -> list[str]:
        return sorted(self._factories)


registry = MaterialRegistry()
