from __future__ import annotations

"""Dependency-light contracts for module-boundary governance.

The governance DTOs are intentionally plain dataclasses so they can be used by
architecture tests, CLI tools, services and GUI controllers without importing
any implementation layer.
"""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ImportBoundaryRule:
    """A declarative import-boundary rule for one source tree slice."""

    key: str
    layer: str
    path_prefix: str
    forbidden_imports: tuple[str, ...] = ()
    allow_files: tuple[str, ...] = ()
    description: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "layer": self.layer,
            "path_prefix": self.path_prefix,
            "forbidden_imports": list(self.forbidden_imports),
            "allow_files": list(self.allow_files),
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ImportBoundaryViolation:
    """One forbidden import found by a boundary audit."""

    rule_key: str
    file: str
    import_name: str
    layer: str
    reason: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_key": self.rule_key,
            "file": self.file,
            "import_name": self.import_name,
            "layer": self.layer,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleBoundaryAuditReport:
    """Result of scanning imports against a boundary policy."""

    ok: bool
    rules: tuple[ImportBoundaryRule, ...] = ()
    checked_file_count: int = 0
    violation_count: int = 0
    violations: tuple[ImportBoundaryViolation, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "checked_file_count": int(self.checked_file_count),
            "violation_count": int(self.violation_count),
            "violations": [item.to_dict() for item in self.violations],
            "warnings": list(self.warnings),
            "rules": [item.to_dict() for item in self.rules],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ModuleGovernanceReport:
    """High-level module-governance status for the current source tree."""

    ok: bool
    module_count: int = 0
    registry_counts: Mapping[str, int] = field(default_factory=dict)
    boundary_audit: ModuleBoundaryAuditReport | None = None
    public_module_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "module_count": int(self.module_count),
            "registry_counts": {str(key): int(value) for key, value in self.registry_counts.items()},
            "public_module_keys": list(self.public_module_keys),
            "boundary_audit": self.boundary_audit.to_dict() if self.boundary_audit else None,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "ImportBoundaryRule",
    "ImportBoundaryViolation",
    "ModuleBoundaryAuditReport",
    "ModuleGovernanceReport",
]
