from __future__ import annotations

"""Dependency-light keyed registry utilities for module plugins.

The objects in this module are intentionally small and serialisable.  They form
one common description language for mesh generators, solver backends, material
providers, runtime compilers and result postprocessors.
"""

from dataclasses import dataclass, field
from typing import Callable, Generic, Iterable, Mapping, Protocol, TypeVar, runtime_checkable


@runtime_checkable
class KeyedPlugin(Protocol):
    key: str


T = TypeVar("T", bound=KeyedPlugin)


@dataclass(frozen=True, slots=True)
class PluginDependencyStatus:
    """Availability of one optional dependency needed by a plugin."""

    name: str
    available: bool = True
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "available": bool(self.available), "detail": self.detail}


@dataclass(frozen=True, slots=True)
class PluginHealth:
    """Runtime health and dependency status for a plugin."""

    available: bool = True
    status: str = "available"
    diagnostics: tuple[str, ...] = ()
    dependencies: tuple[PluginDependencyStatus, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "available": bool(self.available),
            "status": str(self.status),
            "diagnostics": list(self.diagnostics),
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


@dataclass(frozen=True, slots=True)
class PluginCapability:
    """Normalised capability envelope shared by every module plugin."""

    key: str
    label: str = ""
    category: str = "plugin"
    version: str = "1"
    features: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()
    supported_inputs: tuple[str, ...] = ()
    supported_outputs: tuple[str, ...] = ()
    health: PluginHealth = field(default_factory=PluginHealth)
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return bool(self.health.available)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": str(self.key),
            "label": str(self.label or self.key),
            "category": str(self.category),
            "version": str(self.version),
            "available": bool(self.available),
            "features": list(self.features),
            "devices": list(self.devices),
            "supported_inputs": list(self.supported_inputs),
            "supported_outputs": list(self.supported_outputs),
            "health": self.health.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    key: str
    label: str = ""
    category: str = "plugin"
    version: str = "1"
    available: bool = True
    capabilities: Mapping[str, object] = field(default_factory=dict)
    health: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": str(self.key),
            "label": str(self.label or self.key),
            "category": str(self.category),
            "version": str(self.version),
            "available": bool(self.available),
            "capabilities": dict(self.capabilities),
            "health": dict(self.health),
            "metadata": dict(self.metadata),
        }


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return (str(value),)


def normalize_plugin_capability(plugin: object, *, category: str = "plugin") -> PluginCapability:
    """Return a :class:`PluginCapability` for any registered plugin object."""

    key = str(getattr(plugin, "key", plugin.__class__.__name__))
    label = str(getattr(plugin, "label", key))
    raw = getattr(plugin, "capabilities", None)
    if isinstance(raw, PluginCapability):
        return raw
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
    if not isinstance(raw, Mapping):
        raw = {}

    health_raw = raw.get("health", getattr(plugin, "health", None))
    if isinstance(health_raw, PluginHealth):
        health = health_raw
    elif isinstance(health_raw, Mapping):
        dependencies: list[PluginDependencyStatus] = []
        for item in health_raw.get("dependencies", ()) or ():
            if isinstance(item, PluginDependencyStatus):
                dependencies.append(item)
            elif isinstance(item, Mapping):
                dependencies.append(
                    PluginDependencyStatus(
                        name=str(item.get("name", "dependency")),
                        available=bool(item.get("available", True)),
                        detail=str(item.get("detail", "")),
                    )
                )
        health = PluginHealth(
            available=bool(health_raw.get("available", raw.get("available", True))),
            status=str(health_raw.get("status", "available")),
            diagnostics=_as_tuple(health_raw.get("diagnostics", ())),
            dependencies=tuple(dependencies),
        )
    else:
        health = PluginHealth(available=bool(raw.get("available", True)))

    features = raw.get("features") or raw.get("supported_features") or ()
    devices = raw.get("devices") or ()
    supported_inputs = raw.get("supported_inputs") or raw.get("supported_source_types") or raw.get("supported_mesh_kinds") or ()
    supported_outputs = raw.get("supported_outputs") or ()
    metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata", {}), Mapping) else {}

    return PluginCapability(
        key=str(raw.get("key", key)),
        label=str(raw.get("label", label)),
        category=str(raw.get("category", category)),
        version=str(raw.get("version", getattr(plugin, "version", "1"))),
        features=_as_tuple(features),
        devices=_as_tuple(devices),
        supported_inputs=_as_tuple(supported_inputs),
        supported_outputs=_as_tuple(supported_outputs),
        health=health,
        metadata=dict(metadata),
    )


def describe_plugin(plugin: object, *, category: str = "plugin") -> dict[str, object]:
    capability = normalize_plugin_capability(plugin, category=category)
    capability_dict = capability.to_dict()
    return PluginDescriptor(
        key=capability.key,
        label=capability.label,
        category=capability.category,
        version=capability.version,
        available=capability.available,
        capabilities=capability_dict,
        health=capability.health.to_dict(),
        metadata=capability_dict.get("metadata", {}),
    ).to_dict()


class PluginRegistry(Generic[T]):
    """Small deterministic registry used by adapters and module facades.

    The registry intentionally has no implementation-package imports.  Concrete
    modules can compose it to expose replaceable backends without leaking their
    internal classes across module boundaries.
    """

    def __init__(self, *, category: str = "plugin") -> None:
        self.category = str(category)
        self._items: dict[str, T] = {}

    def register(self, item: T, *, replace: bool = False) -> T:
        key = str(item.key)
        if key in self._items and not replace:
            raise KeyError(f"{self.category} already registered: {key}")
        self._items[key] = item
        return item

    def unregister(self, key: str) -> T:
        try:
            return self._items.pop(str(key))
        except KeyError as exc:
            raise KeyError(self._unknown_message(key)) from exc

    def get(self, key: str) -> T:
        try:
            return self._items[str(key)]
        except KeyError as exc:
            raise KeyError(self._unknown_message(key)) from exc

    def maybe_get(self, key: str) -> T | None:
        return self._items.get(str(key))

    def keys(self) -> list[str]:
        return sorted(self._items)

    def values(self) -> list[T]:
        return [self._items[key] for key in self.keys()]

    def descriptors(self, *, label_getter: Callable[[T], str] | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for item in self.values():
            descriptor = describe_plugin(item, category=self.category)
            if label_getter is not None:
                descriptor["label"] = label_getter(item)
            rows.append(descriptor)
        return rows

    def health(self) -> list[dict[str, object]]:
        return [describe_plugin(item, category=self.category)["health"] for item in self.values()]

    def __contains__(self, key: object) -> bool:
        return str(key) in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterable[T]:
        return iter(self.values())

    def _unknown_message(self, key: object) -> str:
        known = ", ".join(self.keys()) or "<none>"
        return f"Unknown {self.category} {key!r}. Known: {known}"


__all__ = [
    "KeyedPlugin",
    "PluginCapability",
    "PluginDependencyStatus",
    "PluginDescriptor",
    "PluginHealth",
    "PluginRegistry",
    "describe_plugin",
    "normalize_plugin_capability",
]
