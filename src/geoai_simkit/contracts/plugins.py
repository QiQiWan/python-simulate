from __future__ import annotations

"""External plugin entry-point contracts.

These DTOs describe Python package entry points without importing optional
plugin implementations.  They are used by the plugin discovery service,
module-governance reports and GUI/controller status panels.
"""

from dataclasses import dataclass, field
from typing import Mapping

from .payloads import PluginRegistrationPayload


@dataclass(frozen=True, slots=True)
class ExternalPluginGroupSpec:
    """One supported Python entry-point group for GeoAI SimKit plugins."""

    group: str
    registry_key: str
    category: str
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "registry_key": self.registry_key,
            "category": self.category,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ExternalPluginEntryPoint:
    """A discovered entry point before it is loaded."""

    name: str
    group: str
    value: str = ""
    module: str = ""
    attr: str = ""
    distribution: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "group": self.group,
            "value": self.value,
            "module": self.module,
            "attr": self.attr,
            "distribution": self.distribution,
        }


@dataclass(frozen=True, slots=True)
class ExternalPluginLoadIssue:
    """One failure or warning from entry-point loading."""

    severity: str
    group: str
    entry_point: str
    code: str
    message: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return str(self.severity).lower() in {"error", "blocking"}

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "group": self.group,
            "entry_point": self.entry_point,
            "code": self.code,
            "message": self.message,
            "blocking": self.blocking,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExternalPluginLoadRecord:
    """One successfully loaded and registered plugin object."""

    group: str
    entry_point: str
    plugin_key: str
    registry_key: str
    category: str
    replace: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self) -> PluginRegistrationPayload:
        return PluginRegistrationPayload(
            group=self.group,
            registry_key=self.registry_key,
            category=self.category,
            plugin_key=self.plugin_key,
            entry_point=self.entry_point,
            replace=bool(self.replace),
            source="external_entry_point",
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "entry_point": self.entry_point,
            "plugin_key": self.plugin_key,
            "registry_key": self.registry_key,
            "category": self.category,
            "replace": bool(self.replace),
            "metadata": dict(self.metadata),
            "registration_payload": self.to_payload().to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ExternalPluginLoadReport:
    """Result of discovering/loading external plugin entry points."""

    ok: bool
    discovered_count: int = 0
    loaded_count: int = 0
    groups: tuple[ExternalPluginGroupSpec, ...] = ()
    entry_points: tuple[ExternalPluginEntryPoint, ...] = ()
    records: tuple[ExternalPluginLoadRecord, ...] = ()
    issues: tuple[ExternalPluginLoadIssue, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "discovered_count": int(self.discovered_count),
            "loaded_count": int(self.loaded_count),
            "issue_count": self.issue_count,
            "groups": [item.to_dict() for item in self.groups],
            "entry_points": [item.to_dict() for item in self.entry_points],
            "records": [item.to_dict() for item in self.records],
            "issues": [item.to_dict() for item in self.issues],
            "metadata": dict(self.metadata),
        }


__all__ = [
    "ExternalPluginEntryPoint",
    "ExternalPluginGroupSpec",
    "ExternalPluginLoadIssue",
    "ExternalPluginLoadRecord",
    "ExternalPluginLoadReport",
    "PluginRegistrationPayload",
]
