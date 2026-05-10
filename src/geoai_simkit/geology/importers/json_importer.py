from __future__ import annotations

"""Structured JSON adapter for geological project data."""

from pathlib import Path
import json
from typing import Any, Mapping

from geoai_simkit.geology.importers.contracts import GeologyImportDiagnostic, GeologyImportRequest, GeologyImportResult, normalize_source_type
from geoai_simkit.geometry.entities import PointEntity
from geoai_simkit.geoproject import (
    Borehole,
    BoreholeLayer,
    GeoProjectDocument,
    GeometrySurface,
    GeometryVolume,
    MaterialRecord,
    SoilCluster,
    SoilContour,
    SoilLayerSurface,
)


def _safe_id(value: Any, fallback: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in str(value or fallback).strip()]
    out = "".join(chars).strip("_") or fallback
    while "__" in out:
        out = out.replace("__", "_")
    if out[0].isdigit():
        out = f"{fallback}_{out}"
    return out


def _float_tuple(values: Any, *, length: int, scale: float = 1.0) -> tuple[float, ...]:
    row = [float(v) * scale for v in list(values or [])]
    if len(row) != length:
        raise ValueError(f"Expected {length} numeric values, got {len(row)}: {values!r}")
    return tuple(row)


def _load_payload(source: str | Path | Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    if isinstance(source, Mapping):
        return dict(source), None
    path = Path(source)
    try:
        return json.loads(path.read_text(encoding="utf-8")), str(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Geological JSON import failed: invalid JSON in {path}: {exc}") from exc


def _model_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "geological_model" in payload and isinstance(payload["geological_model"], Mapping):
        return dict(payload["geological_model"])
    return dict(payload)


def _scaled_points(points: Any, scale: float) -> list[tuple[float, float, float]]:
    return [_float_tuple(point, length=3, scale=scale) for point in list(points or [])]


def _bounds_from_rows(volumes: list[Mapping[str, Any]], surfaces: list[Mapping[str, Any]], scale: float) -> tuple[float, float, float, float, float, float]:
    bounds_rows: list[tuple[float, float, float, float, float, float]] = []
    for row in volumes:
        if row.get("bounds") is not None:
            bounds_rows.append(_float_tuple(row.get("bounds"), length=6, scale=scale))  # type: ignore[arg-type]
    point_rows: list[tuple[float, float, float]] = []
    for surface in surfaces:
        point_rows.extend(_scaled_points(surface.get("points", []), scale))
    if point_rows:
        xs = [p[0] for p in point_rows]
        ys = [p[1] for p in point_rows]
        zs = [p[2] for p in point_rows]
        bounds_rows.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    if not bounds_rows:
        return (-10.0, 10.0, -10.0, 10.0, -20.0, 0.0)
    return (
        min(row[0] for row in bounds_rows),
        max(row[1] for row in bounds_rows),
        min(row[2] for row in bounds_rows),
        max(row[3] for row in bounds_rows),
        min(row[4] for row in bounds_rows),
        max(row[5] for row in bounds_rows),
    )


class JSONGeologyImporter:
    label = "Structured JSON geological model importer"
    source_types = ("geology_json", "json_geology", "geological_model_v1", "geojson", "json")

    def can_import(self, request: GeologyImportRequest) -> bool:
        if isinstance(request.source, Mapping):
            return True
        path = request.source_path
        return path is not None and path.suffix.lower() in {".json", ".geojson"}

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        payload, source_path = _load_payload(request.source)
        model = _model_payload(payload)
        scale = float(request.options.get("unit_scale", model.get("unit_scale", payload.get("unit_scale", 1.0))) or 1.0)
        name = str(request.options.get("name") or model.get("name") or payload.get("name") or "geological-model")
        project = GeoProjectDocument.create_empty(name=name)
        project.metadata.update({
            "source": "geology_json_importer",
            "geology_import": {"source_type": "geology_json", "source_path": source_path},
            "dirty": True,
        })
        diagnostics: list[GeologyImportDiagnostic] = []

        volumes = [dict(row) for row in list(model.get("volumes", model.get("blocks", [])) or [])]
        surfaces = [dict(row) for row in list(model.get("surfaces", []) or [])]
        materials = [dict(row) for row in list(model.get("materials", []) or [])]
        clusters = [dict(row) for row in list(model.get("layers", model.get("soil_clusters", [])) or [])]
        boreholes = [dict(row) for row in list(model.get("boreholes", []) or [])]

        contour_data = model.get("soil_contour", {})
        if isinstance(contour_data, Mapping) and contour_data:
            project.soil_model.soil_contour = SoilContour(
                id=str(contour_data.get("id", "soil_contour")),
                name=str(contour_data.get("name", "Soil contour")),
                polygon=_scaled_points(contour_data.get("polygon", []), scale),
                z_top=float(contour_data.get("z_top", 0.0)) * scale,
                z_bottom=float(contour_data.get("z_bottom", -20.0)) * scale,
                metadata=dict(contour_data.get("metadata", {}) or {}),
            )
        else:
            xmin, xmax, ymin, ymax, zmin, zmax = _bounds_from_rows(volumes, surfaces, scale)
            project.soil_model.soil_contour = SoilContour(
                polygon=[(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)],
                z_top=zmax,
                z_bottom=zmin,
                metadata={"source": "geology_json_bounds"},
            )

        for row in materials:
            material = MaterialRecord.from_dict(row)
            project.material_library.soil_materials[material.id] = material
            project.topology_graph.add_node(material.id, "material", label=material.name, model_type=material.model_type)

        surface_id_map: dict[str, str] = {}
        for surface_index, row in enumerate(surfaces):
            surface_id = _safe_id(row.get("id", row.get("name")), f"surface_{surface_index + 1}")
            for raw_key in (row.get("id"), row.get("name"), surface_id):
                if raw_key:
                    surface_id_map[str(raw_key)] = surface_id
            points = _scaled_points(row.get("points", []), scale)
            point_ids: list[str] = []
            for point_index, point in enumerate(points):
                point_id = _safe_id(f"{surface_id}_p{point_index + 1}", "point")
                project.geometry_model.points[point_id] = PointEntity(
                    id=point_id,
                    x=point[0],
                    y=point[1],
                    z=point[2],
                    metadata={"source": "geology_json", "surface_id": surface_id},
                )
                point_ids.append(point_id)
                project.topology_graph.add_node(point_id, "point", label=point_id)
            project.geometry_model.surfaces[surface_id] = GeometrySurface(
                id=surface_id,
                name=str(row.get("name", surface_id)),
                point_ids=point_ids,
                kind=str(row.get("kind", "geological_surface")),
                metadata={"source": "geology_json", "points": [list(point) for point in points], **dict(row.get("metadata", {}) or {})},
            )
            project.topology_graph.add_node(surface_id, "face", label=str(row.get("name", surface_id)), kind=str(row.get("kind", "geological_surface")))

        volume_id_map: dict[str, str] = {}
        for volume_index, row in enumerate(volumes):
            volume_id = _safe_id(row.get("id", row.get("name")), f"volume_{volume_index + 1}")
            for raw_key in (row.get("id"), row.get("name"), volume_id):
                if raw_key:
                    volume_id_map[str(raw_key)] = volume_id
            bounds = _float_tuple(row.get("bounds"), length=6, scale=scale)
            surface_ids = [surface_id_map.get(str(value), str(value)) for value in list(row.get("surface_ids", []) or [])]
            material_id = None if row.get("material_id") is None else str(row.get("material_id"))
            project.geometry_model.volumes[volume_id] = GeometryVolume(
                id=volume_id,
                name=str(row.get("name", volume_id)),
                bounds=bounds,  # type: ignore[arg-type]
                surface_ids=surface_ids,
                role=str(row.get("role", "soil")),
                material_id=material_id,
                metadata={"source": "geology_json", **dict(row.get("metadata", {}) or {})},
            )
            project.phase_manager.initial_phase.active_blocks.add(volume_id)
            project.topology_graph.add_node(volume_id, "volume", label=str(row.get("name", volume_id)), role=str(row.get("role", "soil")), material_id=material_id)
            for surface_id in surface_ids:
                project.topology_graph.add_edge(volume_id, surface_id, "bounded_by", import_source="geology_json")
            if material_id:
                project.topology_graph.add_edge(volume_id, material_id, "mapped_to", relation_group="volume_material")
                if material_id not in project.material_library.soil_materials:
                    diagnostics.append(
                        GeologyImportDiagnostic(
                            severity="warning",
                            code="missing_material_created",
                            message=f"Volume {volume_id} referenced missing material {material_id}; a placeholder soil material was created.",
                            target=volume_id,
                        )
                    )
                    project.material_library.soil_materials[material_id] = MaterialRecord(
                        id=material_id,
                        name=material_id,
                        model_type="mohr_coulomb_placeholder",
                        parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3},
                        drainage="drained",
                        metadata={"source": "geology_json_placeholder"},
                    )
                    project.topology_graph.add_node(material_id, "material", label=material_id, model_type="mohr_coulomb_placeholder")

        for cluster_index, row in enumerate(clusters):
            cluster_id = _safe_id(row.get("id", row.get("name")), f"cluster_{cluster_index + 1}")
            cluster = SoilCluster(
                id=cluster_id,
                name=str(row.get("name", cluster_id)),
                volume_ids=[volume_id_map.get(str(value), str(value)) for value in list(row.get("volume_ids", []) or [])],
                material_id=str(row.get("material_id", "soil")),
                layer_id=str(row.get("layer_id", cluster_id)),
                drainage=str(row.get("drainage", "drained")),
                metadata={"source": "geology_json", **dict(row.get("metadata", {}) or {})},
            )
            project.soil_model.add_cluster(cluster)
            project.topology_graph.add_node(cluster.id, "cluster", label=cluster.name, material_id=cluster.material_id)
            for volume_id in cluster.volume_ids:
                project.topology_graph.add_edge(cluster.id, volume_id, "owns", import_source="geology_json")

        for surface_index, row in enumerate(list(model.get("soil_layer_surfaces", []) or [])):
            surface = SoilLayerSurface(
                id=_safe_id(row.get("id", row.get("name")), f"layer_surface_{surface_index + 1}"),
                name=str(row.get("name", row.get("id", f"Layer surface {surface_index + 1}"))),
                kind=str(row.get("kind", "interpolated_surface")),
                control_points=_scaled_points(row.get("control_points", row.get("points", [])), scale),
                source_boreholes=[str(value) for value in list(row.get("source_boreholes", []) or [])],
                metadata={"source": "geology_json", **dict(row.get("metadata", {}) or {})},
            )
            project.soil_model.soil_layer_surfaces[surface.id] = surface

        for row in boreholes:
            borehole_id = _safe_id(row.get("id", row.get("name")), "borehole")
            layers = [
                BoreholeLayer(
                    top=float(layer.get("top", 0.0)) * scale,
                    bottom=float(layer.get("bottom", 0.0)) * scale,
                    material_id=str(layer.get("material_id", "soil")),
                    layer_id=str(layer.get("layer_id", "")),
                    description=str(layer.get("description", "")),
                    metadata=dict(layer.get("metadata", {}) or {}),
                )
                for layer in list(row.get("layers", []) or [])
            ]
            project.soil_model.add_borehole(
                Borehole(
                    id=borehole_id,
                    name=str(row.get("name", borehole_id)),
                    x=float(row.get("x", 0.0)) * scale,
                    y=float(row.get("y", 0.0)) * scale,
                    z=float(row.get("z", 0.0)) * scale,
                    layers=layers,
                    metadata={"source": "geology_json", **dict(row.get("metadata", {}) or {})},
                )
            )

        if volumes:
            project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
            project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] = True
        else:
            diagnostics.append(
                GeologyImportDiagnostic(
                    severity="warning",
                    code="no_volumes",
                    message="Geological JSON import contained no volumes; soil and surface records were imported without a meshable volume.",
                    target=source_path or "inline",
                )
            )
        project.metadata["geology_import_summary"] = {
            "source_type": "geology_json",
            "source_path": source_path,
            "volume_count": len(project.geometry_model.volumes),
            "surface_count": len(project.geometry_model.surfaces),
            "borehole_count": len(project.soil_model.boreholes),
            "material_count": len(project.material_library.soil_materials),
        }
        return GeologyImportResult(
            source_type=normalize_source_type(request.normalized_source_type or "geology_json"),
            source_path=source_path,
            project=project,
            diagnostics=diagnostics,
            imported_object_count=(
                len(project.geometry_model.volumes)
                + len(project.geometry_model.surfaces)
                + len(project.soil_model.boreholes)
                + len(project.soil_model.soil_clusters)
            ),
            metadata=dict(project.metadata["geology_import_summary"]),
        )


__all__ = ["JSONGeologyImporter"]
