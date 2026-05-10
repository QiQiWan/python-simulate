from __future__ import annotations

"""STL adapter for the unified geological importer interface."""

from dataclasses import fields
from pathlib import Path
from typing import Any

from geoai_simkit.geometry.stl_loader import STLImportOptions
from geoai_simkit.geology.importers.contracts import GeologyImportDiagnostic, GeologyImportRequest, GeologyImportResult, normalize_source_type
from geoai_simkit.geoproject import GeoProjectDocument


class STLGeologyImporter:
    label = "STL geological surface importer"
    source_types = ("stl_geology", "stl", "geology_stl", "stl_surface")

    def can_import(self, request: GeologyImportRequest) -> bool:
        path = request.source_path
        return path is not None and path.suffix.lower() == ".stl"

    def _options(self, values: dict[str, Any]) -> STLImportOptions:
        allowed = {field.name for field in fields(STLImportOptions)}
        return STLImportOptions(**{key: value for key, value in dict(values or {}).items() if key in allowed})

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        path = request.source_path
        if path is None:
            raise ValueError("STL geological import requires a filesystem path, not an inline mapping.")
        options = self._options(request.options)
        project_name = request.options.get("project_name") or request.options.get("document_name")
        project = GeoProjectDocument.from_stl_geology(path, options=options, name=None if project_name is None else str(project_name))
        summary = dict(project.metadata.get("stl_geology", {}) or {})
        quality = dict(summary.get("quality", {}) or {})
        diagnostics = [
            GeologyImportDiagnostic(
                severity="warning",
                code="stl_quality_warning",
                message=str(message),
                target=str(path),
            )
            for message in list(quality.get("warnings", []) or [])
        ]
        return GeologyImportResult(
            source_type=normalize_source_type(request.normalized_source_type or "stl_geology"),
            source_path=str(Path(path)),
            project=project,
            diagnostics=diagnostics,
            imported_object_count=int(summary.get("triangle_count", 0) or 0),
            metadata={"summary": summary, "importer": self.label},
        )


__all__ = ["STLGeologyImporter"]
