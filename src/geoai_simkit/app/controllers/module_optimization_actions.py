from __future__ import annotations

"""Qt-free controller for selecting and optimizing individual modules."""

from dataclasses import dataclass, field
from typing import Mapping

from geoai_simkit.services.module_optimization import (
    build_module_optimization_plan,
    build_module_optimization_readiness_report,
    module_optimization_targets,
)


@dataclass(slots=True)
class ModuleOptimizationActionController:
    """Expose module optimization readiness to GUI, CLI and automation callers."""

    metadata: Mapping[str, object] = field(default_factory=dict)

    def readiness_report(self) -> dict[str, object]:
        payload = build_module_optimization_readiness_report().to_dict()
        if self.metadata:
            payload.setdefault("metadata", {}).update(dict(self.metadata))
        return payload

    def target_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for target in module_optimization_targets():
            rows.append(
                {
                    "module_key": target.module_key,
                    "label": target.label,
                    "ready": target.ready,
                    "readiness_score": target.readiness_score,
                    "primary_focus": target.primary_focus,
                    "plugin_group_count": len(target.plugin_groups),
                    "entrypoint_count": len(target.public_entrypoints),
                    "legacy_boundary_count": len(target.legacy_boundaries),
                }
            )
        return rows

    def optimization_plan(self, module_key: str, *, focus: str = "balanced") -> dict[str, object]:
        payload = build_module_optimization_plan(module_key, focus=focus).to_dict()
        if self.metadata:
            payload.setdefault("metadata", {}).update(dict(self.metadata))
        return payload


__all__ = ["ModuleOptimizationActionController"]
