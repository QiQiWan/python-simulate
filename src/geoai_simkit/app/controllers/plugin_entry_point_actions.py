from __future__ import annotations

"""Qt-free controller for external plugin entry-point status panels."""

from typing import Any

from geoai_simkit.services.plugin_entry_points import (
    discover_external_plugin_entry_points,
    load_external_plugins,
    supported_external_plugin_group_dicts,
)


class PluginEntryPointActionController:
    """Small GUI-facing adapter over the headless entry-point service."""

    def supported_groups(self) -> list[dict[str, Any]]:
        return supported_external_plugin_group_dicts()

    def discover(self) -> dict[str, Any]:
        return discover_external_plugin_entry_points().to_dict()

    def load(self, *, replace: bool = False) -> dict[str, Any]:
        return load_external_plugins(replace=replace).to_dict()

    def table_rows(self, *, load: bool = False) -> list[dict[str, Any]]:
        report = load_external_plugins() if load else discover_external_plugin_entry_points()
        rows: list[dict[str, Any]] = []
        for entry in report.entry_points:
            rows.append(
                {
                    "group": entry.group,
                    "name": entry.name,
                    "value": entry.value,
                    "distribution": entry.distribution,
                    "status": "loaded" if any(record.entry_point == entry.name and record.group == entry.group for record in report.records) else "discovered",
                }
            )
        return rows


__all__ = ["PluginEntryPointActionController"]
