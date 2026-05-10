from __future__ import annotations

"""Material model plugin contracts."""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MaterialModelRequest:
    model_key: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MaterialModelResult:
    model_key: str
    model: object
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.model is not None

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "model_key": self.model_key, "metadata": dict(self.metadata)}


@runtime_checkable
class MaterialModelProvider(Protocol):
    key: str
    label: str

    def supported_model_keys(self) -> tuple[str, ...]:
        ...

    def can_create(self, request: MaterialModelRequest) -> bool:
        ...

    def create_model(self, request: MaterialModelRequest) -> MaterialModelResult:
        ...


class MaterialModelProviderRegistry:
    def __init__(self) -> None:
        self._items: dict[str, MaterialModelProvider] = {}

    def register(self, provider: MaterialModelProvider, *, replace: bool = False) -> None:
        key = str(provider.key)
        if key in self._items and not replace:
            raise KeyError(f"Material model provider already registered: {key}")
        self._items[key] = provider

    def get(self, key: str) -> MaterialModelProvider:
        try:
            return self._items[str(key)]
        except KeyError as exc:
            known = ", ".join(sorted(self._items)) or "<none>"
            raise KeyError(f"Unknown material model provider {key!r}. Known providers: {known}") from exc

    def resolve(self, request: MaterialModelRequest, preferred: str = "auto") -> MaterialModelProvider:
        if preferred and preferred != "auto" and preferred in self._items:
            item = self._items[preferred]
            if item.can_create(request):
                return item
        for item in self._items.values():
            if item.can_create(request):
                return item
        known = ", ".join(sorted(self._items)) or "<none>"
        raise KeyError(f"No material provider can create {request.model_key!r}. Registered providers: {known}")

    def keys(self) -> list[str]:
        return sorted(self._items)

    def supported_model_keys(self) -> list[str]:
        keys: set[str] = set()
        for provider in self._items.values():
            keys.update(str(item) for item in provider.supported_model_keys())
        return sorted(keys)

    def descriptors(self) -> list[dict[str, object]]:
        from .registry import describe_plugin

        rows: list[dict[str, object]] = []
        for key in self.keys():
            provider = self._items[key]
            row = describe_plugin(provider, category="material_model_provider")
            row.setdefault("capabilities", {})["supported_model_keys"] = list(provider.supported_model_keys())
            rows.append(row)
        return rows


__all__ = [
    "MaterialModelProvider",
    "MaterialModelProviderRegistry",
    "MaterialModelRequest",
    "MaterialModelResult",
]
