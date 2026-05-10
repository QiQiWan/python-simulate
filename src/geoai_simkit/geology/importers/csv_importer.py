from __future__ import annotations

"""CSV adapter for engineering borehole logs."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geoai_simkit.geology.importers.contracts import GeologyImportDiagnostic, GeologyImportRequest, GeologyImportResult, normalize_source_type
from geoai_simkit.geoproject import (
    Borehole,
    BoreholeLayer,
    GeoProjectDocument,
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


def _header_key(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _first(row: dict[str, str], aliases: tuple[str, ...], default: str = "") -> str:
    for alias in aliases:
        value = row.get(_header_key(alias), "")
        if str(value).strip() != "":
            return str(value).strip()
    return default


def _float_value(row: dict[str, str], aliases: tuple[str, ...], *, default: float | None = None) -> float | None:
    value = _first(row, aliases)
    if value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Expected a numeric value for one of {aliases}, got {value!r}") from exc


def _read_csv_rows(path: Path, *, delimiter: str | None = None) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return []
    dialect = None
    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(text[:2048])
        except csv.Error:
            dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter) if delimiter else csv.DictReader(text.splitlines(), dialect=dialect)
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({_header_key(str(key)): str(value or "").strip() for key, value in dict(raw or {}).items() if key is not None})
    return rows


def _interval_value(
    row: dict[str, str],
    *,
    collar_z: float,
    scale: float,
    mode: str,
    which: str,
    depth_positive_down: bool,
) -> tuple[float, dict[str, Any]]:
    if which == "top":
        elevation_aliases = ("top_elevation", "top_elev", "z_top", "from_elevation")
        depth_aliases = ("top_depth", "depth_top", "from_depth", "depth_from")
        generic_aliases = ("top", "from")
    else:
        elevation_aliases = ("bottom_elevation", "bottom_elev", "z_bottom", "to_elevation")
        depth_aliases = ("bottom_depth", "depth_bottom", "to_depth", "depth_to")
        generic_aliases = ("bottom", "to")
    elevation = _float_value(row, elevation_aliases)
    if elevation is not None:
        return elevation * scale, {"mode": "elevation", "raw": elevation}
    depth = _float_value(row, depth_aliases)
    if depth is not None:
        dz = depth * scale
        return collar_z - dz if depth_positive_down else collar_z + dz, {"mode": "depth", "raw": depth}
    generic = _float_value(row, generic_aliases)
    if generic is None:
        raise ValueError(f"Borehole CSV row is missing {which} interval value.")
    if mode == "elevation":
        return generic * scale, {"mode": "elevation", "raw": generic}
    dz = generic * scale
    return collar_z - dz if depth_positive_down else collar_z + dz, {"mode": "depth", "raw": generic}


@dataclass(slots=True)
class _LayerRow:
    borehole_id: str
    borehole_name: str
    x: float
    y: float
    z: float
    top: float
    bottom: float
    layer_id: str
    material_id: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BoreholeCSVImporter:
    label = "Engineering borehole CSV importer"
    source_types = ("borehole_csv", "csv_boreholes", "borehole_log_csv", "csv")

    def can_import(self, request: GeologyImportRequest) -> bool:
        path = request.source_path
        return path is not None and path.suffix.lower() == ".csv"

    def _parse_rows(self, request: GeologyImportRequest) -> tuple[list[_LayerRow], str]:
        path = request.source_path
        if path is None:
            raise ValueError("Borehole CSV import requires a filesystem path.")
        delimiter = request.options.get("delimiter")
        rows = _read_csv_rows(path, delimiter=None if delimiter in {None, ""} else str(delimiter))
        scale = float(request.options.get("unit_scale", 1.0) or 1.0)
        mode = str(request.options.get("top_bottom_mode", "depth")).strip().lower()
        if mode not in {"depth", "elevation"}:
            raise ValueError("Borehole CSV option top_bottom_mode must be 'depth' or 'elevation'.")
        depth_positive_down = bool(request.options.get("depth_positive_down", True))
        parsed: list[_LayerRow] = []
        for row_index, row in enumerate(rows, start=2):
            try:
                raw_id = _first(row, ("borehole_id", "bh_id", "hole_id", "borehole", "bh", "id"))
                x = _float_value(row, ("x", "easting", "east", "x_coord", "x_coordinate"))
                y = _float_value(row, ("y", "northing", "north", "y_coord", "y_coordinate"))
                if not raw_id:
                    raw_id = f"BH_{row_index - 1}"
                if x is None or y is None:
                    raise ValueError("Borehole CSV row must include x/y coordinates.")
                z_raw = _float_value(row, ("z", "elevation", "collar_z", "ground_elevation", "ground_level"), default=0.0)
                collar_z = float(z_raw or 0.0) * scale
                top, top_meta = _interval_value(row, collar_z=collar_z, scale=scale, mode=mode, which="top", depth_positive_down=depth_positive_down)
                bottom, bottom_meta = _interval_value(row, collar_z=collar_z, scale=scale, mode=mode, which="bottom", depth_positive_down=depth_positive_down)
                if top < bottom:
                    top, bottom = bottom, top
                layer_raw = _first(row, ("layer_id", "layer", "stratum", "stratum_id", "unit", "geologic_unit"))
                material_raw = _first(row, ("material_id", "material", "soil", "soil_type", "lithology"), layer_raw or "soil")
                material_id = _safe_id(material_raw, "soil")
                layer_id = _safe_id(layer_raw or material_id, "layer")
                parsed.append(
                    _LayerRow(
                        borehole_id=_safe_id(raw_id, "borehole"),
                        borehole_name=_first(row, ("borehole_name", "hole_name", "name"), str(raw_id)),
                        x=float(x) * scale,
                        y=float(y) * scale,
                        z=collar_z,
                        top=float(top),
                        bottom=float(bottom),
                        layer_id=layer_id,
                        material_id=material_id,
                        description=_first(row, ("description", "desc", "lithology_description", "remarks", "remark")),
                        metadata={
                            "source_row": row_index,
                            "raw_layer": layer_raw,
                            "raw_material": material_raw,
                            "top": top_meta,
                            "bottom": bottom_meta,
                        },
                    )
                )
            except Exception as exc:
                raise ValueError(f"Borehole CSV import failed at row {row_index}: {exc}") from exc
        return parsed, str(path)

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        rows, source_path = self._parse_rows(request)
        if not rows:
            raise ValueError(f"Borehole CSV import failed: no data rows were found in {source_path}.")
        name = str(request.options.get("name") or request.options.get("project_name") or Path(source_path).stem)
        project = GeoProjectDocument.create_empty(name=name)
        project.metadata.update({
            "source": "borehole_csv_importer",
            "geology_import": {"source_type": "borehole_csv", "source_path": source_path},
            "dirty": True,
        })
        diagnostics: list[GeologyImportDiagnostic] = []

        rows_by_borehole: dict[str, list[_LayerRow]] = {}
        rows_by_layer: dict[str, list[_LayerRow]] = {}
        for row in rows:
            rows_by_borehole.setdefault(row.borehole_id, []).append(row)
            rows_by_layer.setdefault(row.layer_id, []).append(row)

        for borehole_id, borehole_rows in rows_by_borehole.items():
            borehole_rows = sorted(borehole_rows, key=lambda item: item.top, reverse=True)
            first = borehole_rows[0]
            project.soil_model.add_borehole(
                Borehole(
                    id=borehole_id,
                    name=first.borehole_name,
                    x=first.x,
                    y=first.y,
                    z=first.z,
                    layers=[
                        BoreholeLayer(
                            top=row.top,
                            bottom=row.bottom,
                            material_id=row.material_id,
                            layer_id=row.layer_id,
                            description=row.description,
                            metadata=dict(row.metadata),
                        )
                        for row in borehole_rows
                    ],
                    metadata={"source": "borehole_csv", "source_path": source_path},
                )
            )
            project.topology_graph.add_node(borehole_id, "point", label=first.borehole_name, role="borehole", x=first.x, y=first.y, z=first.z)

        material_descriptions: dict[str, str] = {}
        for row in rows:
            material_descriptions.setdefault(row.material_id, row.description)
        for material_id, description in material_descriptions.items():
            project.material_library.soil_materials[material_id] = MaterialRecord(
                id=material_id,
                name=description or material_id,
                model_type=str(request.options.get("default_material_model", "mohr_coulomb_placeholder")),
                parameters=dict(request.options.get("default_material_parameters", {"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3}) or {}),
                drainage=str(request.options.get("default_drainage", "drained")),
                metadata={"source": "borehole_csv_placeholder", "description": description},
            )
            project.topology_graph.add_node(material_id, "material", label=description or material_id, model_type=project.material_library.soil_materials[material_id].model_type)

        xs = [row.x for row in rows]
        ys = [row.y for row in rows]
        z_top = max(max(row.z for row in rows), max(row.top for row in rows))
        z_bottom = min(row.bottom for row in rows)
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        padding = float(request.options.get("xy_padding", max(span * 0.1, 5.0)) or 0.0)
        xmin, xmax = min(xs) - padding, max(xs) + padding
        ymin, ymax = min(ys) - padding, max(ys) + padding
        project.soil_model.soil_contour = SoilContour(
            id="soil_contour_from_boreholes",
            name="Soil contour from borehole extent",
            polygon=[(xmin, ymin, z_top), (xmax, ymin, z_top), (xmax, ymax, z_top), (xmin, ymax, z_top)],
            z_top=z_top,
            z_bottom=z_bottom,
            metadata={"source": "borehole_csv_extent", "xy_padding": padding},
        )

        create_initial_volumes = bool(request.options.get("create_initial_volumes", True))
        for layer_id, layer_rows in rows_by_layer.items():
            top_points = [(row.x, row.y, row.top) for row in layer_rows]
            bottom_points = [(row.x, row.y, row.bottom) for row in layer_rows]
            source_boreholes = sorted({row.borehole_id for row in layer_rows})
            material_ids = sorted({row.material_id for row in layer_rows})
            material_id = material_ids[0]
            if len(material_ids) > 1:
                diagnostics.append(
                    GeologyImportDiagnostic(
                        severity="warning",
                        code="mixed_layer_materials",
                        message=f"Layer {layer_id} references multiple materials; {material_id} is used for the initial volume partition.",
                        target=layer_id,
                        metadata={"material_ids": material_ids},
                    )
                )
            top_surface_id = f"layer_{layer_id}_top"
            bottom_surface_id = f"layer_{layer_id}_bottom"
            project.soil_model.soil_layer_surfaces[top_surface_id] = SoilLayerSurface(
                id=top_surface_id,
                name=f"{layer_id} top",
                kind="borehole_control_surface",
                control_points=top_points,
                source_boreholes=source_boreholes,
                metadata={"source": "borehole_csv", "layer_id": layer_id, "surface_role": "top"},
            )
            project.soil_model.soil_layer_surfaces[bottom_surface_id] = SoilLayerSurface(
                id=bottom_surface_id,
                name=f"{layer_id} bottom",
                kind="borehole_control_surface",
                control_points=bottom_points,
                source_boreholes=source_boreholes,
                metadata={"source": "borehole_csv", "layer_id": layer_id, "surface_role": "bottom"},
            )
            project.topology_graph.add_node(top_surface_id, "face", label=top_surface_id, role="soil_layer_surface")
            project.topology_graph.add_node(bottom_surface_id, "face", label=bottom_surface_id, role="soil_layer_surface")
            if create_initial_volumes:
                volume_id = f"volume_{layer_id}"
                bounds = (xmin, xmax, ymin, ymax, min(row.bottom for row in layer_rows), max(row.top for row in layer_rows))
                project.geometry_model.volumes[volume_id] = GeometryVolume(
                    id=volume_id,
                    name=f"{layer_id} initial partition",
                    bounds=bounds,
                    surface_ids=[top_surface_id, bottom_surface_id],
                    role="soil",
                    material_id=material_id,
                    metadata={"source": "borehole_csv", "layer_id": layer_id, "source_boreholes": source_boreholes},
                )
                project.soil_model.add_cluster(
                    SoilCluster(
                        id=f"cluster_{layer_id}",
                        name=f"{layer_id} cluster",
                        volume_ids=[volume_id],
                        material_id=material_id,
                        layer_id=layer_id,
                        drainage=str(request.options.get("default_drainage", "drained")),
                        metadata={"source": "borehole_csv", "source_boreholes": source_boreholes},
                    )
                )
                project.phase_manager.initial_phase.active_blocks.add(volume_id)
                project.topology_graph.add_node(volume_id, "volume", label=volume_id, role="soil", material_id=material_id)
                project.topology_graph.add_edge(volume_id, material_id, "mapped_to", relation_group="volume_material")
                project.topology_graph.add_edge(volume_id, top_surface_id, "bounded_by", import_source="borehole_csv")
                project.topology_graph.add_edge(volume_id, bottom_surface_id, "bounded_by", import_source="borehole_csv")

        if create_initial_volumes:
            project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
            project.mesh_model.mesh_settings.metadata["requires_volume_meshing"] = True
        else:
            diagnostics.append(
                GeologyImportDiagnostic(
                    severity="warning",
                    code="initial_volumes_disabled",
                    message="Borehole CSV import created boreholes and layer control surfaces without initial volume partitions.",
                    target=source_path,
                )
            )
        project.metadata["geology_import_summary"] = {
            "source_type": "borehole_csv",
            "source_path": source_path,
            "borehole_count": len(project.soil_model.boreholes),
            "layer_surface_count": len(project.soil_model.soil_layer_surfaces),
            "volume_count": len(project.geometry_model.volumes),
            "soil_cluster_count": len(project.soil_model.soil_clusters),
            "material_count": len(project.material_library.soil_materials),
        }
        return GeologyImportResult(
            source_type=normalize_source_type(request.normalized_source_type or "borehole_csv"),
            source_path=source_path,
            project=project,
            diagnostics=diagnostics,
            imported_object_count=len(rows) + len(project.geometry_model.volumes) + len(project.soil_model.soil_layer_surfaces),
            metadata=dict(project.metadata["geology_import_summary"]),
        )


__all__ = ["BoreholeCSVImporter"]
