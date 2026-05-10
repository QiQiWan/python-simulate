from __future__ import annotations

"""Qt-free controller for modular-governance status panels."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services import audit_import_boundaries, build_module_governance_report


@dataclass(slots=True)
class ModuleGovernanceActionController:
    """Expose module-boundary governance reports without importing GUI frameworks."""

    metadata: dict[str, Any] | None = None

    def boundary_audit(self) -> dict[str, Any]:
        return audit_import_boundaries().to_dict()

    def governance_report(self) -> dict[str, Any]:
        report = build_module_governance_report().to_dict()
        if self.metadata:
            report.setdefault("metadata", {}).update(self.metadata)
        return report


__all__ = ["ModuleGovernanceActionController"]
