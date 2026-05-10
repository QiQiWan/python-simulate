from __future__ import annotations

"""Contracts for complete modularization governance.

The DTOs in this module describe the system as a set of independently
interoperable modules.  They intentionally avoid importing implementation
objects so the same report can be used by tests, CLI tools, GUI status panels
and external plugin validators.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModuleLayerSpec:
    """One architectural layer and its import direction policy."""

    key: str
    label: str
    order: int
    allowed_downstream_layers: tuple[str, ...] = ()
    description: str = ""
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "order": int(self.order),
            "allowed_downstream_layers": list(self.allowed_downstream_layers),
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleInterfaceContract:
    """Stable public interface for one module."""

    module_key: str
    entrypoints: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    plugin_groups: tuple[str, ...] = ()
    service_entrypoints: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "module_key": self.module_key,
            "entrypoints": list(self.entrypoints),
            "contracts": list(self.contracts),
            "plugin_groups": list(self.plugin_groups),
            "service_entrypoints": list(self.service_entrypoints),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Complete modular manifest for one public module."""

    key: str
    label: str
    responsibility: str
    layer: str = "modules"
    owned_namespaces: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    interface: ModuleInterfaceContract | None = None
    status: str = "stable"
    legacy_boundary: bool = False
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "responsibility": self.responsibility,
            "layer": self.layer,
            "owned_namespaces": list(self.owned_namespaces),
            "depends_on": list(self.depends_on),
            "interface": self.interface.to_dict() if self.interface else None,
            "status": self.status,
            "legacy_boundary": bool(self.legacy_boundary),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleDependencyEdge:
    """Directed dependency between public modules."""

    source: str
    target: str
    kind: str = "declared"
    allowed: bool = True
    reason: str = ""
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "allowed": bool(self.allowed),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class LegacyBoundaryMarker:
    """A known legacy implementation island with an explicit bridge path."""

    key: str
    path: str
    owner_module: str
    isolation: str
    replacement_target: str = ""
    status: str = "contained"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "path": self.path,
            "owner_module": self.owner_module,
            "isolation": self.isolation,
            "replacement_target": self.replacement_target,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CompleteModularizationReport:
    """System-level report proving the modular architecture is closed."""

    ok: bool
    version: str = "complete_modularization_v1"
    layers: tuple[ModuleLayerSpec, ...] = ()
    modules: tuple[ModuleManifest, ...] = ()
    dependency_edges: tuple[ModuleDependencyEdge, ...] = ()
    legacy_boundaries: tuple[LegacyBoundaryMarker, ...] = ()
    plugin_registry_counts: Mapping[str, int] = field(default_factory=dict)
    external_plugin_groups: tuple[str, ...] = ()
    issue_count: int = 0
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "version": self.version,
            "layers": [item.to_dict() for item in self.layers],
            "modules": [item.to_dict() for item in self.modules],
            "dependency_edges": [item.to_dict() for item in self.dependency_edges],
            "legacy_boundaries": [item.to_dict() for item in self.legacy_boundaries],
            "plugin_registry_counts": {str(key): int(value) for key, value in self.plugin_registry_counts.items()},
            "external_plugin_groups": list(self.external_plugin_groups),
            "issue_count": int(self.issue_count),
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "CompleteModularizationReport",
    "LegacyBoundaryMarker",
    "ModuleDependencyEdge",
    "ModuleInterfaceContract",
    "ModuleLayerSpec",
    "ModuleManifest",
]
