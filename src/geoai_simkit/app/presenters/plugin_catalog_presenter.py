from __future__ import annotations

"""Formatting helpers for displaying plugin registry health in the GUI."""

from typing import Any, Mapping


def format_plugin_catalog_rows(catalog: Mapping[str, list[Mapping[str, Any]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, items in catalog.items():
        for item in items:
            health = item.get("health", {}) if isinstance(item.get("health", {}), Mapping) else {}
            rows.append(
                {
                    "category": str(category),
                    "key": str(item.get("key", "")),
                    "label": str(item.get("label", item.get("key", ""))),
                    "available": "yes" if bool(item.get("available", health.get("available", True))) else "no",
                    "status": str(health.get("status", "available")),
                }
            )
    return rows


__all__ = ["format_plugin_catalog_rows"]
