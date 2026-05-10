from __future__ import annotations

"""Geology-domain services and import adapters."""

from importlib import import_module
from typing import Any

from geoai_simkit.geology.layer_surfaces import (
    InterpolatedSurfaceGrid,
    LayerSurfaceInterpolationResult,
    interpolate_control_points_to_grid,
    interpolate_project_layer_surfaces,
)

_LAZY_EXPORTS = {
    "GeologyImportDiagnostic": ("geoai_simkit.geology.importers", "GeologyImportDiagnostic"),
    "GeologyImportRequest": ("geoai_simkit.geology.importers", "GeologyImportRequest"),
    "GeologyImportResult": ("geoai_simkit.geology.importers", "GeologyImportResult"),
    "GeologyImporter": ("geoai_simkit.geology.importers", "GeologyImporter"),
    "GeologyImporterRegistry": ("geoai_simkit.geology.importers", "GeologyImporterRegistry"),
    "get_default_geology_importer_registry": ("geoai_simkit.geology.importers", "get_default_geology_importer_registry"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'geoai_simkit.geology' has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "GeologyImportDiagnostic",
    "GeologyImportRequest",
    "GeologyImportResult",
    "GeologyImporter",
    "GeologyImporterRegistry",
    "InterpolatedSurfaceGrid",
    "LayerSurfaceInterpolationResult",
    "get_default_geology_importer_registry",
    "interpolate_control_points_to_grid",
    "interpolate_project_layer_surfaces",
]
