from __future__ import annotations

"""Stable facade for geological body import workflows."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from geoai_simkit.geology.importers import (
    GeologyImportRequest,
    GeologyImportResult,
    GeologyImporter,
    GeologyImporterRegistry,
    get_default_geology_importer_registry,
)
from geoai_simkit.geometry.stl_loader import STLGeologyMesh, STLImportOptions
from geoai_simkit.geometry.stl_loader import load_stl_geology as _load_stl_geology
from geoai_simkit.geoproject import GeoProjectDocument
from geoai_simkit.mesh.multi_region_stl import combine_mesh_documents
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module

MODULE_KEY = "geology_import"


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def importer_registry() -> GeologyImporterRegistry:
    return get_default_geology_importer_registry()


def supported_geology_import_kinds() -> list[str]:
    return importer_registry().supported_source_types()


def importer_summaries() -> list[dict[str, Any]]:
    return importer_registry().importer_summaries()


def register_geology_importer(importer: GeologyImporter, *, replace: bool = False) -> None:
    importer_registry().register(importer, replace=replace)


def import_geology(
    source: str | Path | dict[str, Any],
    *,
    source_type: str | None = None,
    options: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> GeologyImportResult:
    request = GeologyImportRequest(
        source=source,
        source_type=source_type,
        options=dict(options or {}),
        metadata=dict(metadata or {}),
    )
    return importer_registry().import_to_project(request)


def create_project_from_geology(
    source: str | Path | dict[str, Any],
    *,
    source_type: str | None = None,
    options: dict[str, Any] | None = None,
    name: str | None = None,
) -> GeoProjectDocument:
    merged_options = dict(options or {})
    if name is not None:
        merged_options.setdefault("name", name)
        merged_options.setdefault("project_name", name)
    return import_geology(source, source_type=source_type, options=merged_options).project


def _coerce_stl_options(options: STLImportOptions | dict[str, Any] | None) -> STLImportOptions:
    if isinstance(options, STLImportOptions):
        return options
    return STLImportOptions(**dict(options or {}))


def _stl_options_to_dict(options: STLImportOptions | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(options, STLImportOptions):
        return asdict(options)
    return dict(options or {})


def load_geological_stl(path: str | Path, options: STLImportOptions | dict[str, Any] | None = None) -> STLGeologyMesh:
    return _load_stl_geology(path, _coerce_stl_options(options))


def create_project_from_stl(
    path: str | Path,
    options: STLImportOptions | dict[str, Any] | None = None,
    *,
    name: str | None = None,
) -> GeoProjectDocument:
    merged_options = _stl_options_to_dict(options)
    if name is not None:
        merged_options["project_name"] = name
    return import_geology(path, source_type="stl_geology", options=merged_options).project


def import_stl_into_project(
    project: GeoProjectDocument,
    path: str | Path,
    options: STLImportOptions | dict[str, Any] | None = None,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    if replace:
        incoming = create_project_from_stl(path, options)
        project.project_settings = incoming.project_settings
        project.soil_model = incoming.soil_model
        project.geometry_model = incoming.geometry_model
        project.topology_graph = incoming.topology_graph
        project.structure_model = incoming.structure_model
        project.material_library = incoming.material_library
        project.mesh_model = incoming.mesh_model
        project.phase_manager = incoming.phase_manager
        project.solver_model = incoming.solver_model
        project.result_store = incoming.result_store
        project.metadata = incoming.metadata
        return dict(project.metadata.get("stl_geology", project.metadata.get("geology_import_summary", {})))
    result = import_geology(path, source_type="stl_geology", options=_stl_options_to_dict(options))
    incoming = result.project
    for key, value in incoming.geometry_model.surfaces.items():
        project.geometry_model.surfaces[key] = value
    for key, value in incoming.geometry_model.volumes.items():
        project.geometry_model.volumes[key] = value
        project.phase_manager.initial_phase.active_blocks.add(key)
    for key, value in incoming.soil_model.soil_clusters.items():
        project.soil_model.soil_clusters[key] = value
    project.material_library.soil_materials.update(incoming.material_library.soil_materials)
    if incoming.mesh_model.mesh_document is not None:
        existing = project.mesh_model.mesh_document
        incoming_mesh = incoming.mesh_model.mesh_document
        if existing is not None and str(existing.metadata.get("mesh_role", "")) == "geometry_surface" and str(incoming_mesh.metadata.get("mesh_role", "")) == "geometry_surface":
            project.mesh_model.attach_mesh(combine_mesh_documents([existing, incoming_mesh], metadata={"source": "multi_stl_incremental_import"}))
        else:
            project.mesh_model.attach_mesh(incoming_mesh)
    for node_id, node in incoming.topology_graph.nodes.items():
        project.topology_graph.nodes[node_id] = node
    project.topology_graph.edges.extend(incoming.topology_graph.edges)
    project.metadata.setdefault("imported_geology", []).append(result.to_dict())
    project.metadata.setdefault("imported_stl_geology", []).append(dict(result.metadata.get("summary", {})))
    project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
    project.mark_changed(["geometry", "mesh", "soil"], action="import_stl_geology", affected_entities=list(incoming.geometry_model.volumes))
    return dict(result.metadata.get("summary", result.metadata))


def smoke_check() -> dict[str, Any]:
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "registry_available": bool(importer_registry().supported_source_types()),
            "json_importer_available": "geology_json" in importer_registry().supported_source_types(),
            "borehole_csv_importer_available": "borehole_csv" in importer_registry().supported_source_types(),
            "stl_options_available": STLImportOptions().unit_scale == 1.0,
            "loader_callable": callable(_load_stl_geology),
            "project_factory_available": callable(GeoProjectDocument.from_stl_geology),
        },
    )


__all__ = [
    "GeologyImportRequest",
    "GeologyImportResult",
    "GeologyImporter",
    "GeologyImporterRegistry",
    "STLGeologyMesh",
    "STLImportOptions",
    "create_project_from_geology",
    "create_project_from_stl",
    "describe_module",
    "import_geology",
    "import_stl_into_project",
    "importer_registry",
    "importer_summaries",
    "load_geological_stl",
    "register_geology_importer",
    "smoke_check",
    "supported_geology_import_kinds",
]
