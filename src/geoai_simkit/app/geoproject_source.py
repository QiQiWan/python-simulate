from __future__ import annotations

"""GeoProjectDocument data-source helpers for GUI/workbench layers.

The GUI is allowed to receive legacy workbench or engineering objects, but this
module normalizes everything to GeoProjectDocument before any object tree,
property panel, stage editor, material editor or solver compiler reads data.
"""

from typing import Any, Mapping

from geoai_simkit.geoproject import GeoProjectDocument

_CACHE_KEY = "geo_project_document"
_SOURCE_KEY = "geo_project_data_source"


def is_geoproject_document(value: Any) -> bool:
    return isinstance(value, GeoProjectDocument)


def get_geoproject_document(document: Any, *, create_if_missing: bool = True) -> GeoProjectDocument:
    if isinstance(document, GeoProjectDocument):
        document.populate_default_framework_content()
        return document

    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        cached = metadata.get(_CACHE_KEY)
        if isinstance(cached, GeoProjectDocument):
            cached.populate_default_framework_content()
            return cached
        if isinstance(cached, Mapping):
            project = GeoProjectDocument.from_dict(cached)
            project.populate_default_framework_content()
            metadata[_CACHE_KEY] = project
            metadata[_SOURCE_KEY] = "GeoProjectDocument.from_cached_dict"
            return project

    if hasattr(document, "geometry_model") and hasattr(document, "phase_manager"):
        project = document  # type: ignore[assignment]
        project.populate_default_framework_content()
        return project

    if hasattr(document, "geometry") and hasattr(document, "stages"):
        project = GeoProjectDocument.from_engineering_document(document)
        project.populate_default_framework_content()
        if isinstance(metadata, dict):
            metadata[_CACHE_KEY] = project
            metadata[_SOURCE_KEY] = "GeoProjectDocument.from_engineering_document"
        return project

    if hasattr(document, "model"):
        name = getattr(getattr(document, "case", None), "name", None) or getattr(getattr(document, "model", None), "name", "geo-project")
        model_metadata = dict(getattr(getattr(document, "model", None), "metadata", {}) or {})
        stl_payload = model_metadata.get("stl_geology") if isinstance(model_metadata, dict) else None
        case_geometry = getattr(getattr(document, "case", None), "geometry", None)
        stl_path = getattr(case_geometry, "path", None)
        if not stl_path and isinstance(stl_payload, Mapping):
            stl_path = (stl_payload or {}).get("source_path")
        if stl_path:
            try:
                from geoai_simkit.geometry.stl_loader import STLImportOptions

                params = dict(getattr(case_geometry, "parameters", {}) or {})
                project = GeoProjectDocument.from_stl_geology(
                    stl_path,
                    options=STLImportOptions(
                        name=str(params.get("name") or (stl_payload or {}).get("name") or name),
                        unit_scale=float(params.get("unit_scale", (stl_payload or {}).get("unit_scale", 1.0)) or 1.0),
                        merge_tolerance=float(params.get("merge_tolerance", 1.0e-9) or 0.0),
                        role=str(params.get("role", (stl_payload or {}).get("role", "geology_surface"))),
                        material_id=str(params.get("material_id", (stl_payload or {}).get("material_id", "imported_geology"))),
                    ),
                    name=str(name),
                )
                if isinstance(metadata, dict):
                    metadata[_CACHE_KEY] = project
                    metadata[_SOURCE_KEY] = "GeoProjectDocument.from_stl_geology"
                return project
            except Exception as exc:
                if isinstance(metadata, dict):
                    metadata["geoproject_stl_init_error"] = str(exc)

        from geoai_simkit.document import engineering_document_from_simulation_model

        engineering = engineering_document_from_simulation_model(document.model, name=name)
        project = GeoProjectDocument.from_engineering_document(engineering)
        project.populate_default_framework_content()
        if isinstance(metadata, dict):
            metadata[_CACHE_KEY] = project
            metadata[_SOURCE_KEY] = "GeoProjectDocument.from_workbench_model"
        return project

    if not create_if_missing:
        raise TypeError(f"Cannot resolve GeoProjectDocument from {type(document)!r}")
    project = GeoProjectDocument.create_foundation_pit({"dimension": "3d"}, name="gui-geoproject")
    return project


def set_geoproject_document(document: Any, project: GeoProjectDocument) -> GeoProjectDocument:
    if isinstance(document, GeoProjectDocument):
        return project
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        metadata[_CACHE_KEY] = project
        metadata[_SOURCE_KEY] = "GeoProjectDocument"
    return project


def mark_geoproject_dirty(document: Any, project: GeoProjectDocument | None = None) -> None:
    project = project or get_geoproject_document(document)
    project.metadata["dirty"] = True
    if hasattr(document, "dirty"):
        document.dirty = True
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        if document is not project:
            metadata[_CACHE_KEY] = project
        metadata["geoproject_dirty"] = True


def geoproject_summary(project: GeoProjectDocument) -> dict[str, Any]:
    validation = project.validate_framework()
    counts = dict(validation.get("counts", {}) or {})
    return {
        "contract": "geoproject_gui_data_source_v1",
        "project_name": project.project_settings.name,
        "project_id": project.project_settings.project_id,
        "active_phase_id": project.phase_manager.active_phase_id,
        "counts": counts,
        "ok": bool(validation.get("ok")),
        "framework_content_filled": bool(project.metadata.get("framework_content_filled")),
    }


__all__ = [
    "get_geoproject_document",
    "set_geoproject_document",
    "mark_geoproject_dirty",
    "geoproject_summary",
    "is_geoproject_document",
]
