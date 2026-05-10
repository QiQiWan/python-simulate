from __future__ import annotations

"""Qt-free controller for complete modularization status panels."""

from dataclasses import dataclass, field
from typing import Mapping

from geoai_simkit.services.module_kernel import build_complete_modularization_report, module_manifests
from geoai_simkit.services.module_optimization import build_module_optimization_readiness_report


@dataclass(slots=True)
class ModuleKernelActionController:
    """Expose complete module-manifest and modularity reports to GUI/CLI callers."""

    metadata: Mapping[str, object] = field(default_factory=dict)

    def complete_modularization_report(self) -> dict[str, object]:
        report = build_complete_modularization_report().to_dict()
        if self.metadata:
            report.setdefault("metadata", {}).update(dict(self.metadata))
        return report

    def module_manifest_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for manifest in module_manifests():
            interface = manifest.interface
            rows.append(
                {
                    "key": manifest.key,
                    "label": manifest.label,
                    "status": manifest.status,
                    "legacy_boundary": manifest.legacy_boundary,
                    "depends_on": list(manifest.depends_on),
                    "owned_namespace_count": len(manifest.owned_namespaces),
                    "entrypoint_count": len(interface.entrypoints if interface else ()),
                    "plugin_groups": list(interface.plugin_groups if interface else ()),
                }
            )
        return rows

    def module_optimization_readiness(self) -> dict[str, object]:
        payload = build_module_optimization_readiness_report().to_dict()
        if self.metadata:
            payload.setdefault("metadata", {}).update(dict(self.metadata))
        return payload


__all__ = ["ModuleKernelActionController"]
