from __future__ import annotations

"""Importer registry for geological model sources."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geology.importers.contracts import GeologyImporter, GeologyImportRequest, GeologyImportResult, normalize_source_type


@dataclass(slots=True)
class GeologyImporterRegistry:
    _importers: list[GeologyImporter] = field(default_factory=list)

    def register(self, importer: GeologyImporter, *, replace: bool = False) -> None:
        normalized_types = {normalize_source_type(kind) for kind in importer.source_types}
        if replace:
            self._importers = [
                existing
                for existing in self._importers
                if not normalized_types.intersection({normalize_source_type(kind) for kind in existing.source_types})
            ]
        elif any(normalized_types.intersection({normalize_source_type(kind) for kind in existing.source_types}) for existing in self._importers):
            overlap = sorted(
                normalized_types.intersection(
                    {
                        normalize_source_type(kind)
                        for existing in self._importers
                        for kind in existing.source_types
                    }
                )
            )
            raise ValueError(f"Geology importer source type already registered: {', '.join(overlap)}")
        self._importers.append(importer)

    def importer_summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "geology_" + normalize_source_type(importer.source_types[0] if importer.source_types else importer.label),
                "label": importer.label,
                "category": "geology_importer",
                "version": "1",
                "available": True,
                "capabilities": {
                    "key": "geology_" + normalize_source_type(importer.source_types[0] if importer.source_types else importer.label),
                    "label": importer.label,
                    "category": "geology_importer",
                    "version": "1",
                    "available": True,
                    "features": ["import_to_project"],
                    "devices": [],
                    "supported_inputs": [normalize_source_type(kind) for kind in importer.source_types],
                    "supported_outputs": ["GeoProjectDocument"],
                    "health": {"available": True, "status": "available", "diagnostics": [], "dependencies": []},
                    "metadata": {},
                },
                "health": {"available": True, "status": "available", "diagnostics": [], "dependencies": []},
                "metadata": {"source_types": [normalize_source_type(kind) for kind in importer.source_types]},
                "source_types": [normalize_source_type(kind) for kind in importer.source_types],
            }
            for importer in self._importers
        ]

    def supported_source_types(self) -> list[str]:
        out: list[str] = []
        for importer in self._importers:
            for kind in importer.source_types:
                normalized = normalize_source_type(kind)
                if normalized and normalized not in out:
                    out.append(normalized)
        return out

    def resolve(self, request: GeologyImportRequest) -> GeologyImporter:
        requested = request.normalized_source_type
        for importer in self._importers:
            if requested in {normalize_source_type(kind) for kind in importer.source_types}:
                return importer
        for importer in self._importers:
            if importer.can_import(request):
                return importer
        known = ", ".join(self.supported_source_types())
        raise ValueError(f"No geological importer registered for source type {requested!r}. Supported source types: {known}")

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        return self.resolve(request).import_to_project(request)


_DEFAULT_REGISTRY: GeologyImporterRegistry | None = None


def get_default_geology_importer_registry() -> GeologyImporterRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from geoai_simkit.geology.importers.csv_importer import BoreholeCSVImporter
        from geoai_simkit.geology.importers.json_importer import JSONGeologyImporter
        from geoai_simkit.geology.importers.stl_importer import STLGeologyImporter

        registry = GeologyImporterRegistry()
        registry.register(STLGeologyImporter())
        registry.register(JSONGeologyImporter())
        registry.register(BoreholeCSVImporter())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


__all__ = ["GeologyImporterRegistry", "get_default_geology_importer_registry"]
