from __future__ import annotations

"""Stable facade for the shared project document model."""

from typing import Any

from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module

MODULE_KEY = "document_model"


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def create_empty_project(*, name: str = "Untitled Geo Project") -> GeoProjectDocument:
    return GeoProjectDocument.create_empty(name=name)


def create_foundation_pit_project(
    parameters: dict[str, Any] | None = None,
    *,
    name: str = "foundation-pit",
) -> GeoProjectDocument:
    return GeoProjectDocument.create_foundation_pit(parameters or {"dimension": "3d"}, name=name)


def validate_project(project: GeoProjectDocument) -> dict[str, Any]:
    return project.validate_framework()


def smoke_check() -> dict[str, Any]:
    project = create_empty_project(name="module-smoke")
    report = validate_project(project)
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "project_created": project.project_settings.name == "module-smoke",
            "framework_valid": bool(report.get("ok")),
        },
    )


__all__ = [
    "GeoProjectDocument",
    "create_empty_project",
    "create_foundation_pit_project",
    "describe_module",
    "smoke_check",
    "validate_project",
]
