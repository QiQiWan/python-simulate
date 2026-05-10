from __future__ import annotations

"""PLAXIS-style project document model.

The goal of this module is to provide one auditable document root that binds
soil, geometry, topology, structures, materials, meshing, phases, solver input
and results.  It is deliberately dependency-light so the GUI, tests and service
layer can import it without requiring OCC, gmsh, PyVista or a solver backend.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from geoai_simkit.geometry.kernel import GeometryDocument
from geoai_simkit.geometry.entities import BlockEntity, EdgeEntity, PartitionFeature, PointEntity, SurfaceEntity
from geoai_simkit.geometry.topology_graph import TopologyGraph
from geoai_simkit.document.selection import SelectionSet
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.multi_region_stl import combine_mesh_documents
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap
from geoai_simkit.results.result_package import ResultFieldRecord, ResultPackage, StageResult
from geoai_simkit.stage.stage_plan import Stage, StagePlan


CONTRACT_VERSION = "geoproject_document_v1"


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": value}


def _float_tuple(values: Iterable[Any], *, length: int | None = None, default: float = 0.0) -> tuple[float, ...]:
    out = [float(v) for v in list(values or [])]
    if length is not None:
        while len(out) < length:
            out.append(float(default))
        out = out[:length]
    return tuple(out)


def _string_list(values: Iterable[Any] | None) -> list[str]:
    return [str(v) for v in list(values or [])]


@dataclass(slots=True)
class ProjectSettings:
    name: str = "Untitled Geo Project"
    project_id: str = "geo-project"
    unit_system: str = "SI"
    length_unit: str = "m"
    force_unit: str = "kN"
    stress_unit: str = "kPa"
    vertical_axis: str = "z"
    gravity: float = 9.80665
    analysis_type: str = "staged_construction"
    coordinate_reference: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "project_id": self.project_id,
            "unit_system": self.unit_system,
            "length_unit": self.length_unit,
            "force_unit": self.force_unit,
            "stress_unit": self.stress_unit,
            "vertical_axis": self.vertical_axis,
            "gravity": float(self.gravity),
            "analysis_type": self.analysis_type,
            "coordinate_reference": self.coordinate_reference,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ProjectSettings":
        data = dict(data or {})
        return cls(
            name=str(data.get("name", "Untitled Geo Project")),
            project_id=str(data.get("project_id", "geo-project")),
            unit_system=str(data.get("unit_system", "SI")),
            length_unit=str(data.get("length_unit", "m")),
            force_unit=str(data.get("force_unit", "kN")),
            stress_unit=str(data.get("stress_unit", "kPa")),
            vertical_axis=str(data.get("vertical_axis", "z")),
            gravity=float(data.get("gravity", 9.80665)),
            analysis_type=str(data.get("analysis_type", "staged_construction")),
            coordinate_reference=str(data.get("coordinate_reference", "local")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class SoilContour:
    id: str = "soil_contour"
    name: str = "Soil contour"
    polygon: list[tuple[float, float, float]] = field(default_factory=list)
    z_top: float = 0.0
    z_bottom: float = -30.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "polygon": [list(p) for p in self.polygon],
            "z_top": float(self.z_top),
            "z_bottom": float(self.z_bottom),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SoilContour":
        data = dict(data or {})
        return cls(
            id=str(data.get("id", "soil_contour")),
            name=str(data.get("name", "Soil contour")),
            polygon=[_float_tuple(p, length=3) for p in list(data.get("polygon", []) or [])],
            z_top=float(data.get("z_top", 0.0)),
            z_bottom=float(data.get("z_bottom", -30.0)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class BoreholeLayer:
    top: float
    bottom: float
    material_id: str
    layer_id: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "top": float(self.top),
            "bottom": float(self.bottom),
            "material_id": self.material_id,
            "layer_id": self.layer_id,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BoreholeLayer":
        return cls(
            top=float(data.get("top", 0.0)),
            bottom=float(data.get("bottom", 0.0)),
            material_id=str(data.get("material_id", "soil")),
            layer_id=str(data.get("layer_id", "")),
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class Borehole:
    id: str
    name: str
    x: float
    y: float
    z: float = 0.0
    layers: list[BoreholeLayer] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": float(self.x),
            "y": float(self.y),
            "z": float(self.z),
            "layers": [layer.to_dict() for layer in self.layers],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Borehole":
        return cls(
            id=str(data.get("id", data.get("name", "borehole"))),
            name=str(data.get("name", data.get("id", "borehole"))),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
            layers=[BoreholeLayer.from_dict(row) for row in list(data.get("layers", []) or [])],
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class SoilLayerSurface:
    id: str
    name: str
    kind: str = "interpolated_surface"
    control_points: list[tuple[float, float, float]] = field(default_factory=list)
    source_boreholes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "control_points": [list(p) for p in self.control_points],
            "source_boreholes": list(self.source_boreholes),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SoilLayerSurface":
        return cls(
            id=str(data.get("id", data.get("name", "surface"))),
            name=str(data.get("name", data.get("id", "surface"))),
            kind=str(data.get("kind", "interpolated_surface")),
            control_points=[_float_tuple(p, length=3) for p in list(data.get("control_points", []) or [])],
            source_boreholes=_string_list(data.get("source_boreholes", [])),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class SoilCluster:
    id: str
    name: str
    volume_ids: list[str] = field(default_factory=list)
    material_id: str = "soil"
    layer_id: str = ""
    drainage: str = "drained"
    active_stage_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "volume_ids": list(self.volume_ids),
            "material_id": self.material_id,
            "layer_id": self.layer_id,
            "drainage": self.drainage,
            "active_stage_ids": list(self.active_stage_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SoilCluster":
        return cls(
            id=str(data.get("id", data.get("name", "soil_cluster"))),
            name=str(data.get("name", data.get("id", "soil_cluster"))),
            volume_ids=_string_list(data.get("volume_ids", [])),
            material_id=str(data.get("material_id", "soil")),
            layer_id=str(data.get("layer_id", "")),
            drainage=str(data.get("drainage", "drained")),
            active_stage_ids=_string_list(data.get("active_stage_ids", [])),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class WaterCondition:
    id: str
    name: str
    kind: str = "phreatic_level"
    level: float | None = None
    pressure_head: float | None = None
    target_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "level": self.level,
            "pressure_head": self.pressure_head,
            "target_ids": list(self.target_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WaterCondition":
        level = data.get("level", None)
        head = data.get("pressure_head", None)
        return cls(
            id=str(data.get("id", data.get("name", "water"))),
            name=str(data.get("name", data.get("id", "water"))),
            kind=str(data.get("kind", "phreatic_level")),
            level=None if level is None else float(level),
            pressure_head=None if head is None else float(head),
            target_ids=_string_list(data.get("target_ids", [])),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class SoilModel:
    soil_contour: SoilContour = field(default_factory=SoilContour)
    boreholes: dict[str, Borehole] = field(default_factory=dict)
    soil_layer_surfaces: dict[str, SoilLayerSurface] = field(default_factory=dict)
    soil_clusters: dict[str, SoilCluster] = field(default_factory=dict)
    water_conditions: dict[str, WaterCondition] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_borehole(self, borehole: Borehole) -> Borehole:
        self.boreholes[borehole.id] = borehole
        return borehole

    def add_cluster(self, cluster: SoilCluster) -> SoilCluster:
        self.soil_clusters[cluster.id] = cluster
        return cluster

    def add_water_condition(self, condition: WaterCondition) -> WaterCondition:
        self.water_conditions[condition.id] = condition
        return condition

    def to_dict(self) -> dict[str, Any]:
        return {
            "SoilContour": self.soil_contour.to_dict(),
            "Boreholes": [row.to_dict() for row in self.boreholes.values()],
            "SoilLayerSurfaces": [row.to_dict() for row in self.soil_layer_surfaces.values()],
            "SoilClusters": [row.to_dict() for row in self.soil_clusters.values()],
            "WaterConditions": [row.to_dict() for row in self.water_conditions.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SoilModel":
        data = dict(data or {})
        contour_data = data.get("SoilContour", data.get("soil_contour", {}))
        boreholes = [Borehole.from_dict(row) for row in list(data.get("Boreholes", data.get("boreholes", [])) or [])]
        surfaces = [SoilLayerSurface.from_dict(row) for row in list(data.get("SoilLayerSurfaces", data.get("soil_layer_surfaces", [])) or [])]
        clusters = [SoilCluster.from_dict(row) for row in list(data.get("SoilClusters", data.get("soil_clusters", [])) or [])]
        waters = [WaterCondition.from_dict(row) for row in list(data.get("WaterConditions", data.get("water_conditions", [])) or [])]
        return cls(
            soil_contour=SoilContour.from_dict(contour_data),
            boreholes={row.id: row for row in boreholes},
            soil_layer_surfaces={row.id: row for row in surfaces},
            soil_clusters={row.id: row for row in clusters},
            water_conditions={row.id: row for row in waters},
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class GeometryCurve:
    id: str
    name: str
    point_ids: list[str] = field(default_factory=list)
    kind: str = "polyline"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "point_ids": list(self.point_ids), "kind": self.kind, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeometryCurve":
        return cls(
            id=str(data.get("id", data.get("name", "curve"))),
            name=str(data.get("name", data.get("id", "curve"))),
            point_ids=_string_list(data.get("point_ids", [])),
            kind=str(data.get("kind", data.get("role", "polyline"))),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class GeometrySurface:
    id: str
    name: str
    point_ids: list[str] = field(default_factory=list)
    curve_ids: list[str] = field(default_factory=list)
    kind: str = "surface"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "point_ids": list(self.point_ids), "curve_ids": list(self.curve_ids), "kind": self.kind, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeometrySurface":
        return cls(
            id=str(data.get("id", data.get("name", "surface"))),
            name=str(data.get("name", data.get("id", "surface"))),
            point_ids=_string_list(data.get("point_ids", [])),
            curve_ids=_string_list(data.get("curve_ids", [])),
            kind=str(data.get("kind", data.get("role", "surface"))),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class GeometryVolume:
    id: str
    name: str
    bounds: tuple[float, float, float, float, float, float] | None = None
    surface_ids: list[str] = field(default_factory=list)
    role: str = "unknown"
    material_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "surface_ids": list(self.surface_ids),
            "role": self.role,
            "material_id": self.material_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeometryVolume":
        bounds = data.get("bounds", None)
        return cls(
            id=str(data.get("id", data.get("name", "volume"))),
            name=str(data.get("name", data.get("id", "volume"))),
            bounds=None if bounds is None else _float_tuple(bounds, length=6),
            surface_ids=_string_list(data.get("surface_ids", data.get("face_ids", []))),
            role=str(data.get("role", "unknown")),
            material_id=None if data.get("material_id") is None else str(data.get("material_id")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class GeometryModel:
    points: dict[str, PointEntity] = field(default_factory=dict)
    curves: dict[str, GeometryCurve] = field(default_factory=dict)
    surfaces: dict[str, GeometrySurface] = field(default_factory=dict)
    volumes: dict[str, GeometryVolume] = field(default_factory=dict)
    parametric_features: dict[str, PartitionFeature] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def edges(self) -> dict[str, GeometryCurve]:
        return self.curves

    @edges.setter
    def edges(self, value: dict[str, GeometryCurve]) -> None:
        self.curves = value

    @property
    def blocks(self) -> dict[str, GeometryVolume]:
        return self.volumes

    @blocks.setter
    def blocks(self, value: dict[str, GeometryVolume]) -> None:
        self.volumes = value

    @classmethod
    def from_geometry_document(cls, document: GeometryDocument) -> "GeometryModel":
        curves: dict[str, GeometryCurve] = {}
        for edge in document.edges.values():
            curves[edge.id] = GeometryCurve(id=edge.id, name=edge.id, point_ids=list(edge.point_ids), kind=edge.role, metadata=dict(edge.metadata))
        surfaces: dict[str, GeometrySurface] = {}
        for surface in document.surfaces.values():
            curve_ids = [surface.outer_edge_id] if surface.outer_edge_id else []
            curve_ids.extend(list(surface.hole_edge_ids))
            surfaces[surface.id] = GeometrySurface(id=surface.id, name=surface.id, point_ids=list(surface.point_ids), curve_ids=curve_ids, kind=surface.role, metadata=dict(surface.metadata))
        volumes: dict[str, GeometryVolume] = {}
        for block in document.blocks.values():
            volumes[block.id] = GeometryVolume(
                id=block.id,
                name=block.name,
                bounds=tuple(float(v) for v in block.bounds),
                surface_ids=list(block.face_ids),
                role=block.role,
                material_id=block.material_id,
                metadata=dict(block.metadata),
            )
        return cls(
            points=dict(document.points),
            curves=curves,
            surfaces=surfaces,
            volumes=volumes,
            parametric_features=dict(document.partition_features),
            metadata=dict(document.metadata),
        )

    def to_geometry_document(self) -> GeometryDocument:
        edges: dict[str, EdgeEntity] = {}
        surfaces: dict[str, SurfaceEntity] = {}
        blocks: dict[str, BlockEntity] = {}
        for curve in self.curves.values():
            edges[curve.id] = EdgeEntity(id=curve.id, point_ids=tuple(curve.point_ids), role="sketch", metadata={"kind": curve.kind, **dict(curve.metadata)})
        for surface in self.surfaces.values():
            surfaces[surface.id] = SurfaceEntity(id=surface.id, point_ids=tuple(surface.point_ids), role="sketch", metadata={"kind": surface.kind, **dict(surface.metadata)})
        for volume in self.volumes.values():
            if volume.bounds is None:
                continue
            blocks[volume.id] = BlockEntity(
                id=volume.id,
                name=volume.name,
                bounds=tuple(float(v) for v in volume.bounds),
                role="unknown" if not volume.role else volume.role,  # type: ignore[arg-type]
                material_id=volume.material_id,
                metadata=dict(volume.metadata),
            )
        return GeometryDocument(
            points=dict(self.points),
            edges=edges,
            surfaces=surfaces,
            blocks=blocks,
            partition_features=dict(self.parametric_features),
            metadata=dict(self.metadata),
        )

    def add_volume(self, volume: GeometryVolume) -> GeometryVolume:
        self.volumes[volume.id] = volume
        return volume

    def to_dict(self) -> dict[str, Any]:
        return {
            "Points": [row.to_dict() for row in self.points.values()],
            "Curves": [row.to_dict() for row in self.curves.values()],
            "Surfaces": [row.to_dict() for row in self.surfaces.values()],
            "Volumes": [row.to_dict() for row in self.volumes.values()],
            "ParametricFeatures": [row.to_dict() for row in self.parametric_features.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "GeometryModel":
        data = dict(data or {})
        points: dict[str, PointEntity] = {}
        for row in list(data.get("Points", data.get("points", [])) or []):
            row = dict(row)
            pid = str(row.get("id", "point"))
            points[pid] = PointEntity(id=pid, x=float(row.get("x", 0.0)), y=float(row.get("y", 0.0)), z=float(row.get("z", 0.0)), metadata=dict(row.get("metadata", {}) or {}))
        curves = [GeometryCurve.from_dict(row) for row in list(data.get("Curves", data.get("curves", [])) or [])]
        surfaces = [GeometrySurface.from_dict(row) for row in list(data.get("Surfaces", data.get("surfaces", [])) or [])]
        volumes = [GeometryVolume.from_dict(row) for row in list(data.get("Volumes", data.get("volumes", [])) or [])]
        features: dict[str, PartitionFeature] = {}
        for row in list(data.get("ParametricFeatures", data.get("parametric_features", [])) or []):
            row = dict(row)
            fid = str(row.get("id", f"feature_{len(features)+1:03d}"))
            features[fid] = PartitionFeature(
                id=fid,
                type=str(row.get("type", "manual_split")),  # type: ignore[arg-type]
                parameters=dict(row.get("parameters", {}) or {}),
                target_block_ids=tuple(_string_list(row.get("target_block_ids", []))),
                generated_block_ids=tuple(_string_list(row.get("generated_block_ids", []))),
                metadata=dict(row.get("metadata", {}) or {}),
            )
        return cls(
            points=points,
            curves={row.id: row for row in curves},
            surfaces={row.id: row for row in surfaces},
            volumes={row.id: row for row in volumes},
            parametric_features=features,
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class StructureRecord:
    id: str
    name: str
    geometry_ref: str = ""
    material_id: str = ""
    active_stage_ids: list[str] = field(default_factory=list)
    release_policy: str = "fully_bonded"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "geometry_ref": self.geometry_ref,
            "material_id": self.material_id,
            "active_stage_ids": list(self.active_stage_ids),
            "release_policy": self.release_policy,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StructureRecord":
        return cls(
            id=str(data.get("id", data.get("name", "structure"))),
            name=str(data.get("name", data.get("id", "structure"))),
            geometry_ref=str(data.get("geometry_ref", "")),
            material_id=str(data.get("material_id", "")),
            active_stage_ids=_string_list(data.get("active_stage_ids", [])),
            release_policy=str(data.get("release_policy", "fully_bonded")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class AnchorRecord(StructureRecord):
    bonded_length: float = 0.0
    free_length: float = 0.0
    prestress: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        row = super().to_dict()
        row.update({"bonded_length": float(self.bonded_length), "free_length": float(self.free_length), "prestress": float(self.prestress)})
        return row

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AnchorRecord":
        base = StructureRecord.from_dict(data)
        return cls(**base.to_dict(), bonded_length=float(data.get("bonded_length", 0.0)), free_length=float(data.get("free_length", 0.0)), prestress=float(data.get("prestress", 0.0)))


@dataclass(slots=True)
class StructuralInterfaceRecord:
    id: str
    name: str
    master_ref: str = ""
    slave_ref: str = ""
    material_id: str = ""
    contact_mode: str = "frictional"
    active_stage_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "master_ref": self.master_ref,
            "slave_ref": self.slave_ref,
            "material_id": self.material_id,
            "contact_mode": self.contact_mode,
            "active_stage_ids": list(self.active_stage_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StructuralInterfaceRecord":
        return cls(
            id=str(data.get("id", data.get("name", "interface"))),
            name=str(data.get("name", data.get("id", "interface"))),
            master_ref=str(data.get("master_ref", data.get("region_a", ""))),
            slave_ref=str(data.get("slave_ref", data.get("region_b", ""))),
            material_id=str(data.get("material_id", "")),
            contact_mode=str(data.get("contact_mode", "frictional")),
            active_stage_ids=_string_list(data.get("active_stage_ids", data.get("active_stages", []))),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class StructureModel:
    plates: dict[str, StructureRecord] = field(default_factory=dict)
    beams: dict[str, StructureRecord] = field(default_factory=dict)
    embedded_beams: dict[str, StructureRecord] = field(default_factory=dict)
    anchors: dict[str, AnchorRecord] = field(default_factory=dict)
    structural_interfaces: dict[str, StructuralInterfaceRecord] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_plate(self, plate: StructureRecord) -> StructureRecord:
        self.plates[plate.id] = plate
        return plate

    def add_beam(self, beam: StructureRecord) -> StructureRecord:
        self.beams[beam.id] = beam
        return beam

    def add_interface(self, interface: StructuralInterfaceRecord) -> StructuralInterfaceRecord:
        self.structural_interfaces[interface.id] = interface
        return interface

    def to_dict(self) -> dict[str, Any]:
        return {
            "Plates": [row.to_dict() for row in self.plates.values()],
            "Beams": [row.to_dict() for row in self.beams.values()],
            "EmbeddedBeams": [row.to_dict() for row in self.embedded_beams.values()],
            "Anchors": [row.to_dict() for row in self.anchors.values()],
            "StructuralInterfaces": [row.to_dict() for row in self.structural_interfaces.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "StructureModel":
        data = dict(data or {})
        plates = [StructureRecord.from_dict(row) for row in list(data.get("Plates", data.get("plates", [])) or [])]
        beams = [StructureRecord.from_dict(row) for row in list(data.get("Beams", data.get("beams", [])) or [])]
        embedded = [StructureRecord.from_dict(row) for row in list(data.get("EmbeddedBeams", data.get("embedded_beams", [])) or [])]
        anchors = [AnchorRecord.from_dict(row) for row in list(data.get("Anchors", data.get("anchors", [])) or [])]
        interfaces = [StructuralInterfaceRecord.from_dict(row) for row in list(data.get("StructuralInterfaces", data.get("structural_interfaces", [])) or [])]
        return cls(
            plates={row.id: row for row in plates},
            beams={row.id: row for row in beams},
            embedded_beams={row.id: row for row in embedded},
            anchors={row.id: row for row in anchors},
            structural_interfaces={row.id: row for row in interfaces},
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class MaterialRecord:
    id: str
    name: str
    model_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    drainage: str = "not_applicable"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "model_type": self.model_type,
            "parameters": dict(self.parameters),
            "drainage": self.drainage,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialRecord":
        return cls(
            id=str(data.get("id", data.get("name", "material"))),
            name=str(data.get("name", data.get("id", "material"))),
            model_type=str(data.get("model_type", data.get("model", "linear_elastic"))),
            parameters=dict(data.get("parameters", {}) or {}),
            drainage=str(data.get("drainage", "not_applicable")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class DrainageGroundwaterProperty:
    id: str
    name: str
    permeability: tuple[float, float, float] = (1.0e-7, 1.0e-7, 1.0e-7)
    storage: float = 0.0
    unit_weight_water: float = 9.81
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "permeability": list(self.permeability),
            "storage": float(self.storage),
            "unit_weight_water": float(self.unit_weight_water),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DrainageGroundwaterProperty":
        return cls(
            id=str(data.get("id", data.get("name", "drainage"))),
            name=str(data.get("name", data.get("id", "drainage"))),
            permeability=_float_tuple(data.get("permeability", (1.0e-7, 1.0e-7, 1.0e-7)), length=3, default=1.0e-7),
            storage=float(data.get("storage", 0.0)),
            unit_weight_water=float(data.get("unit_weight_water", 9.81)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class MaterialLibrary:
    soil_materials: dict[str, MaterialRecord] = field(default_factory=dict)
    plate_materials: dict[str, MaterialRecord] = field(default_factory=dict)
    beam_materials: dict[str, MaterialRecord] = field(default_factory=dict)
    interface_materials: dict[str, MaterialRecord] = field(default_factory=dict)
    drainage_groundwater_properties: dict[str, DrainageGroundwaterProperty] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_soil_material(self, material: MaterialRecord) -> MaterialRecord:
        self.soil_materials[material.id] = material
        return material

    def material_ids(self) -> set[str]:
        return set(self.soil_materials) | set(self.plate_materials) | set(self.beam_materials) | set(self.interface_materials)

    def to_dict(self) -> dict[str, Any]:
        return {
            "SoilMaterials": [row.to_dict() for row in self.soil_materials.values()],
            "PlateMaterials": [row.to_dict() for row in self.plate_materials.values()],
            "BeamMaterials": [row.to_dict() for row in self.beam_materials.values()],
            "InterfaceMaterials": [row.to_dict() for row in self.interface_materials.values()],
            "DrainageGroundwaterProperties": [row.to_dict() for row in self.drainage_groundwater_properties.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MaterialLibrary":
        data = dict(data or {})
        soils = [MaterialRecord.from_dict(row) for row in list(data.get("SoilMaterials", data.get("soil_materials", [])) or [])]
        plates = [MaterialRecord.from_dict(row) for row in list(data.get("PlateMaterials", data.get("plate_materials", [])) or [])]
        beams = [MaterialRecord.from_dict(row) for row in list(data.get("BeamMaterials", data.get("beam_materials", [])) or [])]
        interfaces = [MaterialRecord.from_dict(row) for row in list(data.get("InterfaceMaterials", data.get("interface_materials", [])) or [])]
        drainage = [DrainageGroundwaterProperty.from_dict(row) for row in list(data.get("DrainageGroundwaterProperties", data.get("drainage_groundwater_properties", [])) or [])]
        return cls(
            soil_materials={row.id: row for row in soils},
            plate_materials={row.id: row for row in plates},
            beam_materials={row.id: row for row in beams},
            interface_materials={row.id: row for row in interfaces},
            drainage_groundwater_properties={row.id: row for row in drainage},
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class MeshSettings:
    element_family: str = "tet4"
    global_size: float = 2.0
    local_size_fields: dict[str, float] = field(default_factory=dict)
    preserve_interfaces: bool = True
    conformal_blocks: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_family": self.element_family,
            "global_size": float(self.global_size),
            "local_size_fields": dict(self.local_size_fields),
            "preserve_interfaces": bool(self.preserve_interfaces),
            "conformal_blocks": bool(self.conformal_blocks),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MeshSettings":
        data = dict(data or {})
        return cls(
            element_family=str(data.get("element_family", "tet4")),
            global_size=float(data.get("global_size", 2.0)),
            local_size_fields={str(k): float(v) for k, v in dict(data.get("local_size_fields", {}) or {}).items()},
            preserve_interfaces=bool(data.get("preserve_interfaces", True)),
            conformal_blocks=bool(data.get("conformal_blocks", True)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class MeshModel:
    mesh_settings: MeshSettings = field(default_factory=MeshSettings)
    mesh_document: MeshDocument | None = None
    mesh_entity_map: MeshEntityMap = field(default_factory=MeshEntityMap)
    quality_report: MeshQualityReport = field(default_factory=MeshQualityReport)
    metadata: dict[str, Any] = field(default_factory=dict)

    def attach_mesh(self, mesh: MeshDocument) -> None:
        self.mesh_document = mesh
        self.mesh_entity_map = mesh.entity_map
        self.quality_report = mesh.quality

    def to_dict(self) -> dict[str, Any]:
        return {
            "MeshSettings": self.mesh_settings.to_dict(),
            "MeshDocument": self.mesh_document.to_dict() if self.mesh_document is not None else None,
            "MeshEntityMap": self.mesh_entity_map.to_dict(),
            "QualityReport": self.quality_report.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MeshModel":
        data = dict(data or {})
        mesh_payload = data.get("MeshDocument", data.get("mesh_document", None))
        mesh = _mesh_document_from_payload(mesh_payload) if isinstance(mesh_payload, Mapping) else None
        model = cls(
            mesh_settings=MeshSettings.from_dict(data.get("MeshSettings", data.get("mesh_settings", {}))),
            mesh_document=mesh,
            mesh_entity_map=_mesh_entity_map_from_payload(data.get("MeshEntityMap", data.get("mesh_entity_map", {}))),
            quality_report=_mesh_quality_from_payload(data.get("QualityReport", data.get("quality_report", {}))),
            metadata=dict(data.get("metadata", {}) or {}),
        )
        if mesh is not None:
            model.mesh_entity_map = mesh.entity_map
            model.quality_report = mesh.quality
        return model


@dataclass(slots=True)
class CalculationSettings:
    calculation_type: str = "plastic"
    deformation_control: bool = True
    max_steps: int = 100
    max_iterations: int = 50
    tolerance: float = 1.0e-5
    reset_displacements: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "calculation_type": self.calculation_type,
            "deformation_control": bool(self.deformation_control),
            "max_steps": int(self.max_steps),
            "max_iterations": int(self.max_iterations),
            "tolerance": float(self.tolerance),
            "reset_displacements": bool(self.reset_displacements),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CalculationSettings":
        data = dict(data or {})
        return cls(
            calculation_type=str(data.get("calculation_type", "plastic")),
            deformation_control=bool(data.get("deformation_control", True)),
            max_steps=int(data.get("max_steps", 100)),
            max_iterations=int(data.get("max_iterations", 50)),
            tolerance=float(data.get("tolerance", 1.0e-5)),
            reset_displacements=bool(data.get("reset_displacements", False)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class PhaseStateSnapshot:
    stage_id: str
    active_volume_ids: list[str] = field(default_factory=list)
    active_structure_ids: list[str] = field(default_factory=list)
    active_interface_ids: list[str] = field(default_factory=list)
    active_load_ids: list[str] = field(default_factory=list)
    water_condition_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "active_volume_ids": list(self.active_volume_ids),
            "active_structure_ids": list(self.active_structure_ids),
            "active_interface_ids": list(self.active_interface_ids),
            "active_load_ids": list(self.active_load_ids),
            "water_condition_id": self.water_condition_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PhaseStateSnapshot":
        return cls(
            stage_id=str(data.get("stage_id", "stage")),
            active_volume_ids=_string_list(data.get("active_volume_ids", [])),
            active_structure_ids=_string_list(data.get("active_structure_ids", [])),
            active_interface_ids=_string_list(data.get("active_interface_ids", [])),
            active_load_ids=_string_list(data.get("active_load_ids", data.get("loads", []))),
            water_condition_id=None if data.get("water_condition_id") is None else str(data.get("water_condition_id")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class PhaseManager:
    initial_phase: Stage = field(default_factory=lambda: Stage(id="initial", name="Initial phase"))
    construction_phases: dict[str, Stage] = field(default_factory=dict)
    calculation_settings: dict[str, CalculationSettings] = field(default_factory=dict)
    phase_state_snapshots: dict[str, PhaseStateSnapshot] = field(default_factory=dict)
    active_phase_id: str = "initial"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stage_plan(cls, plan: StagePlan, *, all_volume_ids: Iterable[str] = ()) -> "PhaseManager":
        all_ids = list(all_volume_ids or [])
        manager = cls(metadata=dict(plan.metadata))
        if plan.order:
            first = plan.stages[plan.order[0]]
            manager.initial_phase = first
            manager.active_phase_id = plan.active_stage_id or first.id
        for sid in plan.order[1:]:
            manager.construction_phases[sid] = plan.stages[sid]
        for sid in plan.order:
            stage = plan.stages[sid]
            active = sorted(plan.active_blocks_for_stage(tuple(all_ids), sid)) if all_ids else sorted(stage.active_blocks)
            manager.calculation_settings[sid] = CalculationSettings(metadata={"source": "StagePlan"})
            manager.phase_state_snapshots[sid] = PhaseStateSnapshot(
                stage_id=sid,
                active_volume_ids=active,
                active_structure_ids=sorted(stage.active_supports),
                active_interface_ids=sorted(stage.active_interfaces),
                active_load_ids=sorted(stage.loads),
                water_condition_id=None if stage.water_level is None else f"water_level_{sid}",
                metadata={"water_level": stage.water_level, **dict(stage.metadata)},
            )
        return manager

    def to_stage_plan(self) -> StagePlan:
        plan = StagePlan()
        plan.add_stage(self.initial_phase)
        for stage in self.construction_phases.values():
            plan.add_stage(stage)
        plan.active_stage_id = self.active_phase_id
        plan.metadata.update(self.metadata)
        return plan

    def add_construction_phase(self, stage: Stage, settings: CalculationSettings | None = None) -> Stage:
        self.construction_phases[stage.id] = stage
        self.calculation_settings[stage.id] = settings or CalculationSettings()
        return stage

    def to_dict(self) -> dict[str, Any]:
        return {
            "InitialPhase": self.initial_phase.to_dict(),
            "ConstructionPhases": [row.to_dict() for row in self.construction_phases.values()],
            "CalculationSettings": {sid: settings.to_dict() for sid, settings in self.calculation_settings.items()},
            "PhaseStateSnapshots": [row.to_dict() for row in self.phase_state_snapshots.values()],
            "active_phase_id": self.active_phase_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PhaseManager":
        data = dict(data or {})
        initial_data = dict(data.get("InitialPhase", data.get("initial_phase", {"id": "initial", "name": "Initial phase"})) or {})
        initial = Stage(
            id=str(initial_data.get("id", "initial")),
            name=str(initial_data.get("name", "Initial phase")),
            predecessor_id=initial_data.get("predecessor_id"),
            active_blocks=set(_string_list(initial_data.get("active_blocks", []))),
            inactive_blocks=set(_string_list(initial_data.get("inactive_blocks", []))),
            active_supports=set(_string_list(initial_data.get("active_supports", []))),
            active_interfaces=set(_string_list(initial_data.get("active_interfaces", []))),
            loads=set(_string_list(initial_data.get("loads", []))),
            water_level=initial_data.get("water_level"),
            metadata=dict(initial_data.get("metadata", {}) or {}),
        )
        manager = cls(initial_phase=initial, active_phase_id=str(data.get("active_phase_id", initial.id)), metadata=dict(data.get("metadata", {}) or {}))
        for row in list(data.get("ConstructionPhases", data.get("construction_phases", [])) or []):
            row = dict(row)
            stage = Stage(
                id=str(row.get("id", row.get("name", "phase"))),
                name=str(row.get("name", row.get("id", "phase"))),
                predecessor_id=row.get("predecessor_id"),
                active_blocks=set(_string_list(row.get("active_blocks", []))),
                inactive_blocks=set(_string_list(row.get("inactive_blocks", []))),
                active_supports=set(_string_list(row.get("active_supports", []))),
                active_interfaces=set(_string_list(row.get("active_interfaces", []))),
                loads=set(_string_list(row.get("loads", []))),
                water_level=row.get("water_level"),
                metadata=dict(row.get("metadata", {}) or {}),
            )
            manager.construction_phases[stage.id] = stage
        for sid, row in dict(data.get("CalculationSettings", data.get("calculation_settings", {})) or {}).items():
            manager.calculation_settings[str(sid)] = CalculationSettings.from_dict(row)
        snapshots = [PhaseStateSnapshot.from_dict(row) for row in list(data.get("PhaseStateSnapshots", data.get("phase_state_snapshots", [])) or [])]
        manager.phase_state_snapshots = {row.stage_id: row for row in snapshots}
        return manager


@dataclass(slots=True)
class BoundaryCondition:
    id: str
    name: str
    target_ids: list[str] = field(default_factory=list)
    dof: str = "ux,uy,uz"
    value: float = 0.0
    stage_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "target_ids": list(self.target_ids), "dof": self.dof, "value": float(self.value), "stage_ids": list(self.stage_ids), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BoundaryCondition":
        return cls(id=str(data.get("id", data.get("name", "bc"))), name=str(data.get("name", data.get("id", "bc"))), target_ids=_string_list(data.get("target_ids", [])), dof=str(data.get("dof", "ux,uy,uz")), value=float(data.get("value", 0.0)), stage_ids=_string_list(data.get("stage_ids", [])), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class LoadRecord:
    id: str
    name: str
    target_ids: list[str] = field(default_factory=list)
    kind: str = "surface_load"
    components: dict[str, float] = field(default_factory=dict)
    stage_ids: list[str] = field(default_factory=list)
    multiplier_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "target_ids": list(self.target_ids), "kind": self.kind, "components": dict(self.components), "stage_ids": list(self.stage_ids), "multiplier_id": self.multiplier_id, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LoadRecord":
        return cls(id=str(data.get("id", data.get("name", "load"))), name=str(data.get("name", data.get("id", "load"))), target_ids=_string_list(data.get("target_ids", [])), kind=str(data.get("kind", "surface_load")), components={str(k): float(v) for k, v in dict(data.get("components", {}) or {}).items()}, stage_ids=_string_list(data.get("stage_ids", [])), multiplier_id=None if data.get("multiplier_id") is None else str(data.get("multiplier_id")), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class RuntimeSettings:
    backend: str = "cpu_sparse"
    nonlinear_strategy: str = "newton_raphson"
    linear_solver: str = "spsolve"
    use_gpu: bool = False
    precision: str = "float64"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "nonlinear_strategy": self.nonlinear_strategy, "linear_solver": self.linear_solver, "use_gpu": bool(self.use_gpu), "precision": self.precision, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "RuntimeSettings":
        data = dict(data or {})
        return cls(backend=str(data.get("backend", "cpu_sparse")), nonlinear_strategy=str(data.get("nonlinear_strategy", "newton_raphson")), linear_solver=str(data.get("linear_solver", "spsolve")), use_gpu=bool(data.get("use_gpu", False)), precision=str(data.get("precision", "float64")), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class CompiledPhaseModel:
    id: str
    phase_id: str
    active_cell_count: int = 0
    active_dof_count: int = 0
    material_state_count: int = 0
    interface_count: int = 0
    mesh_block: dict[str, Any] = field(default_factory=dict)
    element_block: dict[str, Any] = field(default_factory=dict)
    material_block: dict[str, Any] = field(default_factory=dict)
    boundary_block: dict[str, Any] = field(default_factory=dict)
    load_block: dict[str, Any] = field(default_factory=dict)
    interface_block: dict[str, Any] = field(default_factory=dict)
    state_variable_block: dict[str, Any] = field(default_factory=dict)
    solver_control_block: dict[str, Any] = field(default_factory=dict)
    result_request_block: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase_id": self.phase_id,
            "active_cell_count": int(self.active_cell_count),
            "active_dof_count": int(self.active_dof_count),
            "material_state_count": int(self.material_state_count),
            "interface_count": int(self.interface_count),
            "MeshBlock": dict(self.mesh_block),
            "ElementBlock": dict(self.element_block),
            "MaterialBlock": dict(self.material_block),
            "BoundaryBlock": dict(self.boundary_block),
            "LoadBlock": dict(self.load_block),
            "InterfaceBlock": dict(self.interface_block),
            "StateVariableBlock": dict(self.state_variable_block),
            "SolverControlBlock": dict(self.solver_control_block),
            "ResultRequestBlock": dict(self.result_request_block),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompiledPhaseModel":
        data = dict(data or {})
        return cls(
            id=str(data.get("id", data.get("phase_id", "compiled"))),
            phase_id=str(data.get("phase_id", "phase")),
            active_cell_count=int(data.get("active_cell_count", 0)),
            active_dof_count=int(data.get("active_dof_count", 0)),
            material_state_count=int(data.get("material_state_count", 0)),
            interface_count=int(data.get("interface_count", 0)),
            mesh_block=dict(data.get("MeshBlock", data.get("mesh_block", {})) or {}),
            element_block=dict(data.get("ElementBlock", data.get("element_block", {})) or {}),
            material_block=dict(data.get("MaterialBlock", data.get("material_block", {})) or {}),
            boundary_block=dict(data.get("BoundaryBlock", data.get("boundary_block", {})) or {}),
            load_block=dict(data.get("LoadBlock", data.get("load_block", {})) or {}),
            interface_block=dict(data.get("InterfaceBlock", data.get("interface_block", {})) or {}),
            state_variable_block=dict(data.get("StateVariableBlock", data.get("state_variable_block", {})) or {}),
            solver_control_block=dict(data.get("SolverControlBlock", data.get("solver_control_block", {})) or {}),
            result_request_block=dict(data.get("ResultRequestBlock", data.get("result_request_block", {})) or {}),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass(slots=True)
class SolverModel:
    compiled_phase_models: dict[str, CompiledPhaseModel] = field(default_factory=dict)
    boundary_conditions: dict[str, BoundaryCondition] = field(default_factory=dict)
    loads: dict[str, LoadRecord] = field(default_factory=dict)
    runtime_settings: RuntimeSettings = field(default_factory=RuntimeSettings)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_boundary_condition(self, condition: BoundaryCondition) -> BoundaryCondition:
        self.boundary_conditions[condition.id] = condition
        return condition

    def add_load(self, load: LoadRecord) -> LoadRecord:
        self.loads[load.id] = load
        return load

    def to_dict(self) -> dict[str, Any]:
        return {
            "CompiledPhaseModels": [row.to_dict() for row in self.compiled_phase_models.values()],
            "BoundaryConditions": [row.to_dict() for row in self.boundary_conditions.values()],
            "Loads": [row.to_dict() for row in self.loads.values()],
            "RuntimeSettings": self.runtime_settings.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SolverModel":
        data = dict(data or {})
        compiled = [CompiledPhaseModel.from_dict(row) for row in list(data.get("CompiledPhaseModels", data.get("compiled_phase_models", [])) or [])]
        bcs = [BoundaryCondition.from_dict(row) for row in list(data.get("BoundaryConditions", data.get("boundary_conditions", [])) or [])]
        loads = [LoadRecord.from_dict(row) for row in list(data.get("Loads", data.get("loads", [])) or [])]
        return cls(compiled_phase_models={row.id: row for row in compiled}, boundary_conditions={row.id: row for row in bcs}, loads={row.id: row for row in loads}, runtime_settings=RuntimeSettings.from_dict(data.get("RuntimeSettings", data.get("runtime_settings", {}))), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class EngineeringMetricRecord:
    id: str
    name: str
    value: float
    unit: str = ""
    phase_id: str | None = None
    target_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "value": float(self.value), "unit": self.unit, "phase_id": self.phase_id, "target_id": self.target_id, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EngineeringMetricRecord":
        return cls(id=str(data.get("id", data.get("name", "metric"))), name=str(data.get("name", data.get("id", "metric"))), value=float(data.get("value", 0.0)), unit=str(data.get("unit", "")), phase_id=None if data.get("phase_id") is None else str(data.get("phase_id")), target_id=None if data.get("target_id") is None else str(data.get("target_id")), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class ResultCurve:
    id: str
    name: str
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    x_label: str = "stage"
    y_label: str = "value"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "x": list(self.x), "y": list(self.y), "x_label": self.x_label, "y_label": self.y_label, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResultCurve":
        return cls(id=str(data.get("id", data.get("name", "curve"))), name=str(data.get("name", data.get("id", "curve"))), x=[float(v) for v in list(data.get("x", []) or [])], y=[float(v) for v in list(data.get("y", []) or [])], x_label=str(data.get("x_label", "stage")), y_label=str(data.get("y_label", "value")), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class ResultSection:
    id: str
    name: str
    target_ids: list[str] = field(default_factory=list)
    station_values: list[float] = field(default_factory=list)
    result_values: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "target_ids": list(self.target_ids), "station_values": list(self.station_values), "result_values": list(self.result_values), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResultSection":
        return cls(id=str(data.get("id", data.get("name", "section"))), name=str(data.get("name", data.get("id", "section"))), target_ids=_string_list(data.get("target_ids", [])), station_values=[float(v) for v in list(data.get("station_values", []) or [])], result_values=[float(v) for v in list(data.get("result_values", []) or [])], metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class ReportReference:
    id: str
    title: str
    path: str = ""
    kind: str = "markdown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "path": self.path, "kind": self.kind, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReportReference":
        return cls(id=str(data.get("id", data.get("title", "report"))), title=str(data.get("title", data.get("id", "report"))), path=str(data.get("path", "")), kind=str(data.get("kind", "markdown")), metadata=dict(data.get("metadata", {}) or {}))


@dataclass(slots=True)
class ResultStore:
    phase_results: dict[str, StageResult] = field(default_factory=dict)
    engineering_metrics: dict[str, EngineeringMetricRecord] = field(default_factory=dict)
    curves: dict[str, ResultCurve] = field(default_factory=dict)
    sections: dict[str, ResultSection] = field(default_factory=dict)
    reports: dict[str, ReportReference] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result_package(cls, package: ResultPackage | None) -> "ResultStore":
        store = cls()
        if package is None:
            return store
        store.phase_results = dict(package.stage_results)
        store.metadata.update(dict(package.metadata))
        for metric_name in _collect_metric_names(package):
            curve = package.metric_curve(metric_name)
            store.curves[metric_name] = ResultCurve(
                id=metric_name,
                name=metric_name,
                x=[float(i) for i, _ in enumerate(curve)],
                y=[float(v) for _, v in curve],
                x_label="phase_index",
                y_label=metric_name,
                metadata={"stage_ids": [sid for sid, _ in curve]},
            )
            for sid, value in curve:
                mid = f"{sid}:{metric_name}"
                store.engineering_metrics[mid] = EngineeringMetricRecord(id=mid, name=metric_name, value=float(value), phase_id=sid)
        return store

    def to_dict(self) -> dict[str, Any]:
        return {
            "PhaseResults": [row.to_dict() for row in self.phase_results.values()],
            "EngineeringMetrics": [row.to_dict() for row in self.engineering_metrics.values()],
            "Curves": [row.to_dict() for row in self.curves.values()],
            "Sections": [row.to_dict() for row in self.sections.values()],
            "Reports": [row.to_dict() for row in self.reports.values()],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ResultStore":
        data = dict(data or {})
        phase_results = [_stage_result_from_payload(row) for row in list(data.get("PhaseResults", data.get("phase_results", [])) or [])]
        metrics = [EngineeringMetricRecord.from_dict(row) for row in list(data.get("EngineeringMetrics", data.get("engineering_metrics", [])) or [])]
        curves = [ResultCurve.from_dict(row) for row in list(data.get("Curves", data.get("curves", [])) or [])]
        sections = [ResultSection.from_dict(row) for row in list(data.get("Sections", data.get("sections", [])) or [])]
        reports = [ReportReference.from_dict(row) for row in list(data.get("Reports", data.get("reports", [])) or [])]
        return cls(phase_results={row.stage_id: row for row in phase_results}, engineering_metrics={row.id: row for row in metrics}, curves={row.id: row for row in curves}, sections={row.id: row for row in sections}, reports={row.id: row for row in reports}, metadata=dict(data.get("metadata", {}) or {}))


def _mesh_entity_map_from_payload(data: Any) -> MeshEntityMap:
    data = dict(data or {}) if isinstance(data, Mapping) else {}
    return MeshEntityMap(
        block_to_cells={str(k): [int(vv) for vv in list(v or [])] for k, v in dict(data.get("block_to_cells", {}) or {}).items()},
        face_to_faces={str(k): [int(vv) for vv in list(v or [])] for k, v in dict(data.get("face_to_faces", {}) or {}).items()},
        interface_to_faces={str(k): [int(vv) for vv in list(v or [])] for k, v in dict(data.get("interface_to_faces", {}) or {}).items()},
        node_sets={str(k): [int(vv) for vv in list(v or [])] for k, v in dict(data.get("node_sets", {}) or {}).items()},
        metadata=dict(data.get("metadata", {}) or {}),
    )


def _mesh_quality_from_payload(data: Any) -> MeshQualityReport:
    data = dict(data or {}) if isinstance(data, Mapping) else {}
    return MeshQualityReport(
        min_quality=None if data.get("min_quality") is None else float(data.get("min_quality")),
        max_aspect_ratio=None if data.get("max_aspect_ratio") is None else float(data.get("max_aspect_ratio")),
        bad_cell_ids=[int(v) for v in list(data.get("bad_cell_ids", []) or [])],
        warnings=[str(v) for v in list(data.get("warnings", []) or [])],
    )


def _mesh_document_from_payload(data: Mapping[str, Any]) -> MeshDocument:
    entity_map = _mesh_entity_map_from_payload(data.get("entity_map", {}))
    quality = _mesh_quality_from_payload(data.get("quality", {}))
    return MeshDocument(
        nodes=[_float_tuple(p, length=3) for p in list(data.get("nodes", []) or [])],
        cells=[tuple(int(v) for v in list(c or [])) for c in list(data.get("cells", []) or [])],
        cell_types=[str(v) for v in list(data.get("cell_types", []) or [])],
        cell_tags={str(k): list(v or []) for k, v in dict(data.get("cell_tags", {}) or {}).items()},
        face_tags={str(k): list(v or []) for k, v in dict(data.get("face_tags", {}) or {}).items()},
        node_tags={str(k): list(v or []) for k, v in dict(data.get("node_tags", {}) or {}).items()},
        entity_map=entity_map,
        quality=quality,
        metadata=dict(data.get("metadata", {}) or {}),
    )


def _stage_result_from_payload(data: Mapping[str, Any]) -> StageResult:
    data = dict(data or {})
    result = StageResult(
        stage_id=str(data.get("stage_id", "stage")),
        metrics={str(k): float(v) for k, v in dict(data.get("metrics", {}) or {}).items()},
        support_forces={str(k): float(v) for k, v in dict(data.get("support_forces", {}) or {}).items()},
        metadata=dict(data.get("metadata", {}) or {}),
    )
    for row in list(data.get("fields", []) or []):
        row = dict(row or {})
        name = str(row.get("name", f"field_{len(result.fields)+1:03d}"))
        try:
            values = [float(v) for v in list(row.get("values", []) or [])]
        except Exception:
            values = []
        result.fields[name] = ResultFieldRecord(
            name=name,
            stage_id=None if row.get("stage_id") is None else str(row.get("stage_id")),
            association=str(row.get("association", "stage")),  # type: ignore[arg-type]
            values=values,
            entity_ids=_string_list(row.get("entity_ids", [])),
            components=int(row.get("components", 1)),
            metadata=dict(row.get("metadata", {}) or {}),
        )
    return result


def _collect_metric_names(package: ResultPackage) -> list[str]:
    names: list[str] = []
    for stage in package.stage_results.values():
        for key in stage.metrics:
            if key not in names:
                names.append(key)
    return names


@dataclass(slots=True)
class GeoProjectDocument:
    project_settings: ProjectSettings = field(default_factory=ProjectSettings)
    soil_model: SoilModel = field(default_factory=SoilModel)
    geometry_model: GeometryModel = field(default_factory=GeometryModel)
    topology_graph: TopologyGraph = field(default_factory=TopologyGraph)
    structure_model: StructureModel = field(default_factory=StructureModel)
    material_library: MaterialLibrary = field(default_factory=MaterialLibrary)
    mesh_model: MeshModel = field(default_factory=MeshModel)
    phase_manager: PhaseManager = field(default_factory=PhaseManager)
    solver_model: SolverModel = field(default_factory=SolverModel)
    result_store: ResultStore = field(default_factory=ResultStore)
    selection: SelectionSet = field(default_factory=SelectionSet)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def geometry(self) -> GeometryModel:
        return self.geometry_model

    @geometry.setter
    def geometry(self, value: GeometryModel | GeometryDocument) -> None:
        if isinstance(value, GeometryModel):
            self.geometry_model = value
        elif isinstance(value, GeometryDocument):
            self.geometry_model = GeometryModel.from_geometry_document(value)
        else:
            raise TypeError(f"Unsupported geometry assignment: {type(value).__name__}")

    @property
    def stages(self) -> StagePlan:
        return self.phase_manager.to_stage_plan()

    @stages.setter
    def stages(self, value: StagePlan | PhaseManager) -> None:
        if isinstance(value, PhaseManager):
            self.phase_manager = value
        elif isinstance(value, StagePlan):
            self.phase_manager = PhaseManager.from_stage_plan(value, all_volume_ids=self.geometry_model.volumes.keys())
        else:
            raise TypeError(f"Unsupported stages assignment: {type(value).__name__}")

    @classmethod
    def create_empty(cls, *, name: str = "Untitled Geo Project") -> "GeoProjectDocument":
        settings = ProjectSettings(name=name, project_id=_safe_id(name))
        return cls(project_settings=settings, metadata={"contract": CONTRACT_VERSION})

    @classmethod
    def create_foundation_pit(cls, parameters: dict[str, Any] | None = None, *, name: str = "foundation-pit") -> "GeoProjectDocument":
        from geoai_simkit.document.engineering_document import EngineeringDocument

        engineering = EngineeringDocument.create_foundation_pit(parameters or {"dimension": "3d"}, name=name)
        if engineering.mesh is None:
            engineering.generate_preview_mesh()
        try:
            from geoai_simkit.results.engineering_metrics import build_preview_result_package

            engineering.results = build_preview_result_package(engineering)
        except Exception:
            pass
        project = cls.from_engineering_document(engineering)
        project.populate_default_framework_content()
        project.compile_phase_models()
        return project

    @classmethod
    def from_stl_geology(cls, path: str | Path, *, options: Any | None = None, name: str | None = None) -> "GeoProjectDocument":
        from geoai_simkit.geometry.stl_loader import STLImportOptions, load_stl_geology

        opts = options if isinstance(options, STLImportOptions) else STLImportOptions(**dict(options or {}))
        stl = load_stl_geology(path, opts)
        project_name = name or stl.name
        project = cls.create_empty(name=project_name)
        volume_id = _safe_id(stl.name)
        surface_id = f"surface_{volume_id}"
        xmin, xmax, ymin, ymax, zmin, zmax = stl.bounds

        project.project_settings.metadata.update({
            "source": "stl_geology_loader",
            "stl_source_path": stl.source_path,
            "unit_scale": float(stl.unit_scale),
        })
        project.soil_model.soil_contour = SoilContour(
            id="soil_contour_from_stl",
            name="Soil contour from STL bounds",
            polygon=[(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)],
            z_top=float(zmax),
            z_bottom=float(zmin),
            metadata={"source": "stl_bounds"},
        )
        project.geometry_model.surfaces[surface_id] = GeometrySurface(
            id=surface_id,
            name=f"Surface {stl.name}",
            kind="stl_tri_surface",
            metadata={"source": "stl_geology_loader", "stl": stl.to_summary_dict()},
        )
        project.geometry_model.volumes[volume_id] = GeometryVolume(
            id=volume_id,
            name=stl.name,
            bounds=stl.bounds,
            surface_ids=[surface_id],
            role="soil" if stl.role in {"soil", "geology_surface", "geology"} else str(stl.role),
            material_id=stl.material_id,
            metadata={
                "source": "stl_geology_loader",
                "source_path": stl.source_path,
                "surface_mesh_only": True,
                "requires_volume_meshing": True,
                "solid_solver_ready": False,
                "closed_surface": bool(stl.quality.is_closed),
                "quality": stl.quality.to_dict(),
            },
        )
        project.soil_model.add_cluster(SoilCluster(
            id=f"cluster_{volume_id}",
            name=f"Cluster {stl.name}",
            volume_ids=[volume_id],
            material_id=stl.material_id,
            layer_id=volume_id,
            drainage="drained",
            metadata={"source": "stl_geology_loader", "surface_mesh_only": True, "requires_volume_meshing": True, "solid_solver_ready": False, "closed_surface": bool(stl.quality.is_closed)},
        ))
        project.material_library.soil_materials[stl.material_id] = MaterialRecord(
            id=stl.material_id,
            name=stl.material_id,
            model_type="mohr_coulomb_placeholder",
            drainage="drained",
            parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3, "c_ref": 10.0, "phi": 30.0},
            metadata={"source": "stl_import_default"},
        )
        project.mesh_model.mesh_settings.element_family = "tri3_surface"
        project.mesh_model.mesh_settings.metadata.update({
            "mesh_role": "geometry_surface",
            "requires_volume_meshing": True,
            "requires_volume_remesh": True,
            "solid_solver_ready": False,
            "closed_surface": bool(stl.quality.is_closed),
        })
        project.mesh_model.attach_mesh(stl.to_mesh_document(block_id=volume_id))
        project.phase_manager.initial_phase.active_blocks.add(volume_id)
        project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
        project.topology_graph.add_node(volume_id, "volume", label=stl.name, role=stl.role, material_id=stl.material_id)
        project.topology_graph.add_node(surface_id, "face", label=surface_id, role="stl_tri_surface")
        project.topology_graph.add_edge(volume_id, surface_id, "bounded_by", import_source="stl_geology_loader")
        project.topology_graph.add_node(stl.material_id, "material", label=stl.material_id)
        project.topology_graph.add_edge(volume_id, stl.material_id, "mapped_to", relation_group="volume_material")
        project.metadata.update({
            "source": "stl_geology_loader",
            "stl_geology": stl.to_summary_dict(),
            "dirty": True,
            "surface_mesh_only": True,
            "requires_volume_meshing": True,
            "solid_solver_ready": False,
            "closed_surface": bool(stl.quality.is_closed),
        })
        return project

    def import_stl_geology(self, path: str | Path, *, options: Any | None = None, replace: bool = False) -> dict[str, Any]:
        incoming = GeoProjectDocument.from_stl_geology(path, options=options)
        if replace:
            self.project_settings = incoming.project_settings
            self.soil_model = incoming.soil_model
            self.geometry_model = incoming.geometry_model
            self.topology_graph = incoming.topology_graph
            self.structure_model = incoming.structure_model
            self.material_library = incoming.material_library
            self.mesh_model = incoming.mesh_model
            self.phase_manager = incoming.phase_manager
            self.solver_model = incoming.solver_model
            self.result_store = incoming.result_store
            self.metadata = incoming.metadata
        else:
            for key, value in incoming.geometry_model.surfaces.items():
                self.geometry_model.surfaces[key] = value
            for key, value in incoming.geometry_model.volumes.items():
                self.geometry_model.volumes[key] = value
                self.phase_manager.initial_phase.active_blocks.add(key)
            for key, value in incoming.soil_model.soil_clusters.items():
                self.soil_model.soil_clusters[key] = value
            self.material_library.soil_materials.update(incoming.material_library.soil_materials)
            if incoming.mesh_model.mesh_document is not None:
                existing = self.mesh_model.mesh_document
                incoming_mesh = incoming.mesh_model.mesh_document
                if existing is not None and str(existing.metadata.get("mesh_role", "")) == "geometry_surface" and str(incoming_mesh.metadata.get("mesh_role", "")) == "geometry_surface":
                    self.mesh_model.attach_mesh(combine_mesh_documents([existing, incoming_mesh], metadata={"source": "multi_stl_incremental_import"}))
                else:
                    self.mesh_model.attach_mesh(incoming_mesh)
            for node_id, node in incoming.topology_graph.nodes.items():
                self.topology_graph.nodes[node_id] = node
            self.topology_graph.edges.extend(incoming.topology_graph.edges)
            self.metadata.setdefault("imported_stl_geology", []).append(dict(incoming.metadata.get("stl_geology", {})))
            self.refresh_phase_snapshot(self.phase_manager.initial_phase.id)
            self.mark_changed(["geometry", "mesh", "soil"], action="import_stl_geology", affected_entities=list(incoming.geometry_model.volumes))
        return dict(incoming.metadata.get("stl_geology", {}))

    @classmethod
    def from_engineering_document(cls, document: Any) -> "GeoProjectDocument":
        name = str(getattr(document, "name", "geo-project"))
        geometry = GeometryModel.from_geometry_document(document.geometry)
        soil = _infer_soil_model_from_geometry(document.geometry)
        structures = _infer_structure_model(document)
        materials = _infer_material_library(document, soil, structures)
        phase_manager = PhaseManager.from_stage_plan(document.stages, all_volume_ids=geometry.volumes.keys())
        mesh_model = MeshModel()
        if getattr(document, "mesh", None) is not None:
            mesh_model.attach_mesh(document.mesh)
        result_store = ResultStore.from_result_package(getattr(document, "results", None))
        solver = SolverModel(
            boundary_conditions={str(k): BoundaryCondition.from_dict({"id": str(k), **_as_dict(v)}) for k, v in dict(getattr(document, "boundaries", {}) or {}).items()},
            loads={str(k): LoadRecord.from_dict({"id": str(k), **_as_dict(v)}) for k, v in dict(getattr(document, "loads", {}) or {}).items()},
            runtime_settings=RuntimeSettings(metadata={"source": "EngineeringDocument"}),
            metadata={"source": "EngineeringDocument"},
        )
        project = cls(
            project_settings=ProjectSettings(name=name, project_id=_safe_id(name)),
            soil_model=soil,
            geometry_model=geometry,
            topology_graph=document.topology,
            structure_model=structures,
            material_library=materials,
            mesh_model=mesh_model,
            phase_manager=phase_manager,
            solver_model=solver,
            result_store=result_store,
            metadata={"contract": CONTRACT_VERSION, "source": "EngineeringDocument", **dict(getattr(document, "metadata", {}) or {})},
        )
        project.rebuild_generated_by_relations()
        return project

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeoProjectDocument":
        data = dict(data or {})
        return cls(
            project_settings=ProjectSettings.from_dict(data.get("ProjectSettings", data.get("project_settings", {}))),
            soil_model=SoilModel.from_dict(data.get("SoilModel", data.get("soil_model", {}))),
            geometry_model=GeometryModel.from_dict(data.get("GeometryModel", data.get("geometry_model", {}))),
            topology_graph=_topology_from_dict(data.get("TopologyGraph", data.get("topology_graph", {}))),
            structure_model=StructureModel.from_dict(data.get("StructureModel", data.get("structure_model", {}))),
            material_library=MaterialLibrary.from_dict(data.get("MaterialLibrary", data.get("material_library", {}))),
            mesh_model=MeshModel.from_dict(data.get("MeshModel", data.get("mesh_model", {}))),
            phase_manager=PhaseManager.from_dict(data.get("PhaseManager", data.get("phase_manager", {}))),
            solver_model=SolverModel.from_dict(data.get("SolverModel", data.get("solver_model", {}))),
            result_store=ResultStore.from_dict(data.get("ResultStore", data.get("result_store", {}))),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "GeoProjectDocument":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save_json(self, path: str | Path, *, indent: int = 2) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=indent), encoding="utf-8")
        return target

    def phase_ids(self) -> list[str]:
        return [self.phase_manager.initial_phase.id, *self.phase_manager.construction_phases.keys()]

    def phases_in_order(self) -> list[Stage]:
        phases = [self.phase_manager.initial_phase]
        phases.extend(self.phase_manager.construction_phases.values())
        return phases

    def get_phase(self, phase_id: str | None = None) -> Stage:
        resolved = phase_id or self.phase_manager.active_phase_id or self.phase_manager.initial_phase.id
        if resolved == self.phase_manager.initial_phase.id:
            return self.phase_manager.initial_phase
        if resolved in self.phase_manager.construction_phases:
            return self.phase_manager.construction_phases[resolved]
        raise KeyError(f"Phase not found: {resolved}")

    def set_active_phase(self, phase_id: str) -> Stage:
        phase = self.get_phase(phase_id)
        self.phase_manager.active_phase_id = phase.id
        self.metadata["dirty"] = True
        return phase

    def add_phase(self, phase_id: str, *, name: str | None = None, predecessor_id: str | None = None, copy_from: str | None = None) -> Stage:
        if phase_id == self.phase_manager.initial_phase.id or phase_id in self.phase_manager.construction_phases:
            raise ValueError(f"Phase already exists: {phase_id}")
        if copy_from:
            source = self.get_phase(copy_from)
            stage = Stage(
                id=phase_id,
                name=name or phase_id,
                predecessor_id=predecessor_id if predecessor_id is not None else source.id,
                active_blocks=set(source.active_blocks),
                inactive_blocks=set(source.inactive_blocks),
                active_supports=set(source.active_supports),
                active_interfaces=set(source.active_interfaces),
                loads=set(source.loads),
                water_level=source.water_level,
                metadata={"cloned_from": source.id, **dict(source.metadata)},
            )
        else:
            stage = Stage(
                id=phase_id,
                name=name or phase_id,
                predecessor_id=predecessor_id or self.phase_ids()[-1],
                active_blocks=set(self.geometry_model.volumes.keys()),
                metadata={"created_by": "GeoProjectDocument.add_phase"},
            )
        self.phase_manager.add_construction_phase(stage)
        self.refresh_phase_snapshot(stage.id)
        self.metadata["dirty"] = True
        return stage

    def remove_phase(self, phase_id: str) -> dict[str, Any]:
        if phase_id == self.phase_manager.initial_phase.id:
            raise ValueError("Initial phase cannot be removed")
        removed = self.phase_manager.construction_phases.pop(phase_id, None)
        self.phase_manager.calculation_settings.pop(phase_id, None)
        self.phase_manager.phase_state_snapshots.pop(phase_id, None)
        self.solver_model.compiled_phase_models = {k: v for k, v in self.solver_model.compiled_phase_models.items() if v.phase_id != phase_id}
        if self.phase_manager.active_phase_id == phase_id:
            self.phase_manager.active_phase_id = self.phase_manager.initial_phase.id
        self.metadata["dirty"] = True
        return {"removed": phase_id, "ok": removed is not None, "phase_count": len(self.phase_ids())}

    def set_phase_predecessor(self, phase_id: str, predecessor_id: str | None) -> Stage:
        phase = self.get_phase(phase_id)
        phase.predecessor_id = predecessor_id
        self.refresh_phase_snapshot(phase.id)
        self.metadata["dirty"] = True
        return phase

    def refresh_phase_snapshot(self, phase_id: str) -> PhaseStateSnapshot:
        phase = self.get_phase(phase_id)
        all_volumes = set(self.geometry_model.volumes.keys())
        active_volumes = set(phase.active_blocks) if phase.active_blocks else set(all_volumes)
        active_volumes.difference_update(phase.inactive_blocks)
        snapshot = PhaseStateSnapshot(
            stage_id=phase.id,
            active_volume_ids=sorted(active_volumes),
            active_structure_ids=sorted(phase.active_supports),
            active_interface_ids=sorted(phase.active_interfaces),
            active_load_ids=sorted(phase.loads),
            water_condition_id=str(phase.metadata.get("water_condition_id")) if phase.metadata.get("water_condition_id") else (None if phase.water_level is None else f"water_level_{phase.id}"),
            metadata={"water_level": phase.water_level, **dict(phase.metadata)},
        )
        self.phase_manager.phase_state_snapshots[phase.id] = snapshot
        return snapshot

    def set_phase_volume_activation(self, phase_id: str, volume_id: str, active: bool) -> PhaseStateSnapshot:
        if volume_id not in self.geometry_model.volumes:
            raise KeyError(f"Volume not found: {volume_id}")
        phase = self.get_phase(phase_id)
        if active:
            phase.inactive_blocks.discard(volume_id)
            phase.active_blocks.add(volume_id)
        else:
            phase.active_blocks.discard(volume_id)
            phase.inactive_blocks.add(volume_id)
        self.mark_changed(["phase"], action="set_phase_volume_activation", affected_entities=[phase_id, volume_id])
        return self.refresh_phase_snapshot(phase.id)

    def set_phase_structure_activation(self, phase_id: str, structure_id: str, active: bool) -> PhaseStateSnapshot:
        if not self.get_structure_record(structure_id):
            raise KeyError(f"Structure not found: {structure_id}")
        phase = self.get_phase(phase_id)
        if active:
            phase.active_supports.add(structure_id)
        else:
            phase.active_supports.discard(structure_id)
        for record in self.iter_structure_records():
            if record.id == structure_id:
                active_ids = set(record.active_stage_ids)
                if active:
                    active_ids.add(phase_id)
                else:
                    active_ids.discard(phase_id)
                record.active_stage_ids = sorted(active_ids)
                break
        self.mark_changed(["phase", "structure"], action="set_phase_structure_activation", affected_entities=[phase_id, structure_id])
        return self.refresh_phase_snapshot(phase.id)

    def set_phase_interface_activation(self, phase_id: str, interface_id: str, active: bool) -> PhaseStateSnapshot:
        if interface_id not in self.structure_model.structural_interfaces:
            raise KeyError(f"Interface not found: {interface_id}")
        phase = self.get_phase(phase_id)
        if active:
            phase.active_interfaces.add(interface_id)
        else:
            phase.active_interfaces.discard(interface_id)
        interface = self.structure_model.structural_interfaces[interface_id]
        active_ids = set(interface.active_stage_ids)
        if active:
            active_ids.add(phase_id)
        else:
            active_ids.discard(phase_id)
        interface.active_stage_ids = sorted(active_ids)
        self.mark_changed(["phase", "topology"], action="set_phase_interface_activation", affected_entities=[phase_id, interface_id])
        return self.refresh_phase_snapshot(phase.id)

    def set_phase_load_activation(self, phase_id: str, load_id: str, active: bool) -> PhaseStateSnapshot:
        if load_id not in self.solver_model.loads:
            raise KeyError(f"Load not found: {load_id}")
        phase = self.get_phase(phase_id)
        if active:
            phase.loads.add(load_id)
        else:
            phase.loads.discard(load_id)
        load = self.solver_model.loads[load_id]
        stage_ids = set(load.stage_ids)
        if active:
            stage_ids.add(phase_id)
        else:
            stage_ids.discard(phase_id)
        load.stage_ids = sorted(stage_ids)
        self.mark_changed(["phase", "load"], action="set_phase_load_activation", affected_entities=[phase_id, load_id])
        return self.refresh_phase_snapshot(phase.id)

    def set_phase_water_condition(self, phase_id: str, water_condition_id: str | None = None, *, water_level: float | None = None) -> PhaseStateSnapshot:
        phase = self.get_phase(phase_id)
        if water_condition_id is not None and water_condition_id not in self.soil_model.water_conditions:
            self.soil_model.water_conditions[water_condition_id] = WaterCondition(id=water_condition_id, name=water_condition_id, level=water_level, target_ids=list(self.soil_model.soil_clusters), metadata={"created_by": "set_phase_water_condition"})
        if water_condition_id is not None:
            condition = self.soil_model.water_conditions[water_condition_id]
            if water_level is not None:
                condition.level = float(water_level)
            phase.water_level = condition.level
            phase.metadata["water_condition_id"] = water_condition_id
        else:
            phase.water_level = None if water_level is None else float(water_level)
            phase.metadata.pop("water_condition_id", None)
        self.mark_changed(["phase", "water"], action="set_phase_water_condition", affected_entities=[phase_id, water_condition_id or "water_level"])
        return self.refresh_phase_snapshot(phase.id)

    def iter_structure_records(self) -> Iterable[StructureRecord]:
        yield from self.structure_model.plates.values()
        yield from self.structure_model.beams.values()
        yield from self.structure_model.embedded_beams.values()
        yield from self.structure_model.anchors.values()

    def get_structure_record(self, structure_id: str) -> StructureRecord | None:
        for record in self.iter_structure_records():
            if record.id == structure_id:
                return record
        return None

    def set_structure_material(self, structure_id: str, material_id: str, *, category: str | None = None) -> StructureRecord:
        record = self.get_structure_record(structure_id)
        if record is None:
            raise KeyError(f"Structure not found: {structure_id}")
        resolved_category = (category or "").lower().strip()
        if not resolved_category:
            if structure_id in self.structure_model.plates:
                resolved_category = "plate"
            elif structure_id in self.structure_model.beams or structure_id in self.structure_model.embedded_beams or structure_id in self.structure_model.anchors:
                resolved_category = "beam"
            else:
                resolved_category = "beam"
        if resolved_category == "plate" and material_id not in self.material_library.plate_materials:
            self.material_library.plate_materials[material_id] = MaterialRecord(id=material_id, name=material_id, model_type="elastic_plate", parameters={"EA": 1.0e7, "EI": 1.0e5}, metadata={"created_by": "set_structure_material"})
        elif resolved_category in {"beam", "embedded_beam", "anchor"} and material_id not in self.material_library.beam_materials:
            self.material_library.beam_materials[material_id] = MaterialRecord(id=material_id, name=material_id, model_type="elastic_beam", parameters={"EA": 1.0e6}, metadata={"created_by": "set_structure_material"})
        elif resolved_category == "interface" and material_id not in self.material_library.interface_materials:
            self.material_library.interface_materials[material_id] = MaterialRecord(id=material_id, name=material_id, model_type="interface_frictional", parameters={"R_inter": 0.67}, metadata={"created_by": "set_structure_material"})
        record.material_id = material_id
        self.topology_graph.add_node(material_id, "material", label=material_id)
        self.topology_graph.add_edge(structure_id, material_id, "mapped_to", relation_group="structure_material")
        self.mark_changed(["material", "structure"], action="set_structure_material", affected_entities=[structure_id, material_id])
        return record

    def set_interface_material(self, interface_id: str, material_id: str) -> StructuralInterfaceRecord:
        interface = self.structure_model.structural_interfaces.get(interface_id)
        if interface is None:
            raise KeyError(f"Interface not found: {interface_id}")
        if material_id not in self.material_library.interface_materials:
            self.material_library.interface_materials[material_id] = MaterialRecord(id=material_id, name=material_id, model_type="interface_frictional", parameters={"R_inter": 0.67}, metadata={"created_by": "set_interface_material"})
        interface.material_id = material_id
        self.topology_graph.add_node(material_id, "material", label=material_id)
        self.topology_graph.add_edge(interface_id, material_id, "mapped_to", relation_group="interface_material")
        self.mark_changed(["material", "topology"], action="set_interface_material", affected_entities=[interface_id, material_id])
        return interface

    def mark_changed(self, scopes: Iterable[str], *, action: str = "edit", affected_entities: Iterable[str] = (), message: str = "", metadata: dict[str, Any] | None = None) -> None:
        from geoai_simkit.geoproject.transaction import mark_geoproject_changed

        mark_geoproject_changed(self, scopes, action=action, affected_entities=affected_entities, message=message, metadata=metadata)

    def set_volume_material(self, volume_id: str, material_id: str) -> GeometryVolume:
        volume = self.geometry_model.volumes.get(volume_id)
        if volume is None:
            raise KeyError(f"Volume not found: {volume_id}")
        if material_id not in self.material_library.material_ids():
            self.material_library.soil_materials[material_id] = MaterialRecord(
                id=material_id,
                name=material_id,
                model_type="mohr_coulomb_placeholder",
                drainage="drained",
                parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3, "c_ref": 10.0, "phi": 30.0},
                metadata={"created_by": "set_volume_material"},
            )
        volume.material_id = material_id
        for cluster in self.soil_model.soil_clusters.values():
            if volume_id in cluster.volume_ids:
                cluster.material_id = material_id
        self.topology_graph.add_node(material_id, "material", label=material_id)
        self.topology_graph.add_edge(volume_id, material_id, "mapped_to", relation_group="volume_material")
        self.metadata["dirty"] = True
        return volume

    def upsert_material(self, category: str, material: MaterialRecord) -> MaterialRecord:
        bucket = str(category).lower().strip()
        if bucket in {"soil", "soilmaterial", "soil_material", "soil_materials"}:
            self.material_library.soil_materials[material.id] = material
        elif bucket in {"plate", "plate_material", "plate_materials"}:
            self.material_library.plate_materials[material.id] = material
        elif bucket in {"beam", "beam_material", "beam_materials"}:
            self.material_library.beam_materials[material.id] = material
        elif bucket in {"interface", "interface_material", "interface_materials"}:
            self.material_library.interface_materials[material.id] = material
        else:
            raise ValueError(f"Unknown material category: {category}")
        self.topology_graph.add_node(material.id, "material", label=material.name, model_type=material.model_type)
        self.metadata["dirty"] = True
        return material

    def set_mesh_global_size(self, size: float) -> MeshSettings:
        self.mesh_model.mesh_settings.global_size = float(size)
        self.mesh_model.metadata["mesh_dirty"] = True
        self.metadata["dirty"] = True
        return self.mesh_model.mesh_settings

    def populate_default_framework_content(self) -> "GeoProjectDocument":
        if not self.soil_model.boreholes:
            polygon = self.soil_model.soil_contour.polygon or [(-30.0, -12.0, 0.0), (30.0, -12.0, 0.0), (30.0, 12.0, 0.0), (-30.0, 12.0, 0.0)]
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            ztop = self.soil_model.soil_contour.z_top
            zbot = self.soil_model.soil_contour.z_bottom
            depth = abs(float(ztop - zbot)) or 30.0
            layer_specs = [(ztop, ztop - 0.35 * depth, "soft_clay"), (ztop - 0.35 * depth, ztop - 0.70 * depth, "silty_clay"), (ztop - 0.70 * depth, zbot, "dense_sand")]
            for idx, (x, y) in enumerate(((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)), start=1):
                self.soil_model.add_borehole(Borehole(
                    id=f"BH{idx:02d}",
                    name=f"BH-{idx:02d}",
                    x=float(x), y=float(y), z=float(ztop),
                    layers=[BoreholeLayer(top=a, bottom=b, material_id=m, layer_id=m) for a, b, m in layer_specs],
                    metadata={"source": "default_framework"},
                ))
        if not self.soil_model.soil_layer_surfaces:
            source_boreholes = list(self.soil_model.boreholes)
            levels = sorted({layer.bottom for bh in self.soil_model.boreholes.values() for layer in bh.layers}, reverse=True)
            polygon = self.soil_model.soil_contour.polygon
            for idx, level in enumerate(levels[:-1] if len(levels) > 1 else levels, start=1):
                self.soil_model.soil_layer_surfaces[f"layer_surface_{idx:02d}"] = SoilLayerSurface(
                    id=f"layer_surface_{idx:02d}", name=f"Layer interface {idx:02d}",
                    control_points=[(p[0], p[1], float(level)) for p in polygon],
                    source_boreholes=source_boreholes,
                    metadata={"source": "borehole_layer_defaults"},
                )
        for material_id, params in {
            "soft_clay": {"gamma_unsat": 17.5, "gamma_sat": 18.8, "E_ref": 12000.0, "nu": 0.35, "c_ref": 12.0, "phi": 22.0},
            "silty_clay": {"gamma_unsat": 18.2, "gamma_sat": 19.4, "E_ref": 22000.0, "nu": 0.32, "c_ref": 18.0, "phi": 26.0},
            "dense_sand": {"gamma_unsat": 19.0, "gamma_sat": 20.5, "E_ref": 45000.0, "nu": 0.28, "c_ref": 2.0, "phi": 34.0},
        }.items():
            if material_id not in self.material_library.soil_materials:
                self.material_library.soil_materials[material_id] = MaterialRecord(id=material_id, name=material_id.replace("_", " ").title(), model_type="mohr_coulomb", drainage="drained", parameters=params, metadata={"source": "default_framework"})
        if not self.soil_model.soil_clusters and self.geometry_model.volumes:
            soil_volumes = [v.id for v in self.geometry_model.volumes.values() if v.role in {"soil", "excavation", "rock", "unknown"}]
            if soil_volumes:
                self.soil_model.add_cluster(SoilCluster(id="cluster_soft_clay", name="Soft clay cluster", volume_ids=soil_volumes, material_id="soft_clay", layer_id="soft_clay", drainage="drained", metadata={"source": "default_framework"}))
        if not self.structure_model.structural_interfaces:
            for index, edge in enumerate(self.topology_graph.contact_edges(), start=1):
                a = edge.source; b = edge.target
                va = self.geometry_model.volumes.get(a); vb = self.geometry_model.volumes.get(b)
                roles = {getattr(va, "role", ""), getattr(vb, "role", "")}
                if roles & {"wall", "support", "structure"}:
                    iid = f"interface_{index:03d}"
                    self.structure_model.structural_interfaces[iid] = StructuralInterfaceRecord(id=iid, name=f"Interface {index:03d}", master_ref=a, slave_ref=b, material_id="default_interface", contact_mode="frictional", metadata={"source": "contact_candidates", **dict(edge.attributes)})
        if "default_interface" not in self.material_library.interface_materials:
            self.material_library.interface_materials["default_interface"] = MaterialRecord(id="default_interface", name="Default interface", model_type="interface_frictional", parameters={"R_inter": 0.67, "kn": 1.0e6, "ks": 5.0e5}, metadata={"source": "default_framework"})
        if not self.solver_model.boundary_conditions:
            volume_ids = list(self.geometry_model.volumes)
            self.solver_model.boundary_conditions["bc_bottom_fixed"] = BoundaryCondition(id="bc_bottom_fixed", name="Bottom fixed", target_ids=volume_ids, dof="ux,uy,uz", value=0.0, stage_ids=self.phase_ids(), metadata={"location": "bottom"})
            self.solver_model.boundary_conditions["bc_lateral_roller"] = BoundaryCondition(id="bc_lateral_roller", name="Lateral roller", target_ids=volume_ids, dof="un", value=0.0, stage_ids=self.phase_ids(), metadata={"location": "lateral"})
        if not self.solver_model.loads:
            self.solver_model.loads["load_surface_surcharge"] = LoadRecord(id="load_surface_surcharge", name="Surface surcharge", target_ids=list(self.geometry_model.surfaces), kind="surface_load", components={"qz": -20.0}, stage_ids=self.phase_ids(), metadata={"unit": "kPa"})
        for phase_id in self.phase_ids():
            self.phase_manager.calculation_settings.setdefault(phase_id, CalculationSettings(metadata={"source": "default_framework"}))
            self.refresh_phase_snapshot(phase_id)
        if not self.result_store.sections:
            wall_targets = [item.geometry_ref for item in self.structure_model.plates.values() if item.geometry_ref]
            self.result_store.sections["sec_wall_deflection"] = ResultSection(id="sec_wall_deflection", name="Wall deflection control section", target_ids=wall_targets, station_values=[0.0, 0.25, 0.5, 0.75, 1.0], result_values=[0.0, 0.3, 1.0, 0.6, 0.0], metadata={"quantity": "ux"})
            self.result_store.sections["sec_ground_settlement"] = ResultSection(id="sec_ground_settlement", name="Ground settlement control section", target_ids=list(self.geometry_model.surfaces), station_values=[-30.0, -15.0, 0.0, 15.0, 30.0], result_values=[0.0, -2.0, -5.0, -2.0, 0.0], metadata={"quantity": "uz"})
        if not self.result_store.reports:
            self.result_store.reports["framework_readiness"] = ReportReference(id="framework_readiness", title="GeoProjectDocument framework readiness", path="reports/geoproject_framework_readiness.md", kind="markdown", metadata={"source": "default_framework"})
        self.rebuild_generated_by_relations()
        for volume in self.geometry_model.volumes.values():
            self.topology_graph.add_node(volume.id, "volume", label=volume.name, role=volume.role, material_id=volume.material_id)
            if volume.material_id:
                self.topology_graph.add_node(volume.material_id, "material", label=volume.material_id)
                self.topology_graph.add_edge(volume.id, volume.material_id, "mapped_to", relation_group="volume_material")
        for stage in self.phases_in_order():
            self.topology_graph.add_node(stage.id, "stage", label=stage.name)
            snapshot = self.phase_manager.phase_state_snapshots.get(stage.id)
            if snapshot:
                for vid in snapshot.active_volume_ids:
                    self.topology_graph.add_edge(vid, stage.id, "activated_by")
        for bc in self.solver_model.boundary_conditions.values():
            self.topology_graph.add_node(bc.id, "boundary", label=bc.name, dof=bc.dof)
        for load in self.solver_model.loads.values():
            self.topology_graph.add_node(load.id, "load", label=load.name, kind=load.kind)
        self.metadata["framework_content_filled"] = True
        return self

    def rebuild_generated_by_relations(self) -> None:
        for feature in self.geometry_model.parametric_features.values():
            self.topology_graph.add_node(feature.id, "feature", label=feature.id, feature_type=feature.type)
            for bid in feature.target_block_ids:
                self.topology_graph.add_edge(feature.id, str(bid), "derived_from", feature_type=feature.type)
            for bid in feature.generated_block_ids:
                self.topology_graph.add_edge(str(bid), feature.id, "generated_by", feature_type=feature.type)
        for cluster in self.soil_model.soil_clusters.values():
            self.topology_graph.add_node(cluster.id, "cluster", label=cluster.name, role="soil_cluster", material_id=cluster.material_id)
            for vid in cluster.volume_ids:
                self.topology_graph.add_edge(cluster.id, str(vid), "owns", relation_group="soil_cluster_volume")
        for interface in self.structure_model.structural_interfaces.values():
            self.topology_graph.add_node(interface.id, "interface", label=interface.name, contact_mode=interface.contact_mode)
            if interface.master_ref:
                self.topology_graph.add_edge(interface.id, interface.master_ref, "connected_to", side="master")
            if interface.slave_ref:
                self.topology_graph.add_edge(interface.id, interface.slave_ref, "connected_to", side="slave")

    def compile_phase_models(self) -> dict[str, CompiledPhaseModel]:
        """Compile phase-wise solver input skeletons from the GeoProjectDocument.

        This is not yet a nonlinear FEM assembly, but it is a real data contract:
        mesh nodes, element connectivity, material references, boundary/load
        blocks, active interfaces, state-variable slots and result requests are
        all explicitly written into each CompiledPhaseModel.
        """

        mesh = self.mesh_model.mesh_document
        node_rows = [] if mesh is None else [list(map(float, xyz)) for xyz in mesh.nodes]
        cell_rows = [] if mesh is None else [list(map(int, cell)) for cell in mesh.cells]
        cell_types = [] if mesh is None else list(mesh.cell_types or [self.mesh_model.mesh_settings.element_family] * len(cell_rows))
        block_tags = [] if mesh is None else [str(v) for v in mesh.cell_tags.get("block_id", [])]
        all_materials: dict[str, MaterialRecord] = {}
        all_materials.update(self.material_library.soil_materials)
        all_materials.update(self.material_library.plate_materials)
        all_materials.update(self.material_library.beam_materials)
        all_materials.update(self.material_library.interface_materials)

        for phase_id in self.phase_ids():
            snapshot = self.phase_manager.phase_state_snapshots.get(phase_id) or self.refresh_phase_snapshot(phase_id)
            active_volume_ids = set(snapshot.active_volume_ids) if snapshot.active_volume_ids else set(self.geometry_model.volumes)
            solid_cell_types = {"tet4", "tet4_preview", "tet10", "hex8", "hex8_preview", "hex20", "wedge6", "pyramid5"}
            surface_cell_types = {"tri3", "quad4", "line2"}
            if mesh is not None and block_tags:
                candidate_cell_ids = [idx for idx, block_id in enumerate(block_tags) if block_id in active_volume_ids]
            elif mesh is not None:
                candidate_cell_ids = list(range(len(cell_rows)))
            else:
                candidate_cell_ids = list(range(len(active_volume_ids)))
            if mesh is not None:
                active_cell_ids = [idx for idx in candidate_cell_ids if str(cell_types[idx] if idx < len(cell_types) else self.mesh_model.mesh_settings.element_family).lower() in solid_cell_types]
                surface_cell_ids = [idx for idx in candidate_cell_ids if str(cell_types[idx] if idx < len(cell_types) else "").lower() in surface_cell_types]
            else:
                active_cell_ids = candidate_cell_ids
                surface_cell_ids = []

            if mesh is not None:
                element_rows = []
                for cell_id in active_cell_ids:
                    block_id = block_tags[cell_id] if cell_id < len(block_tags) else ""
                    volume = self.geometry_model.volumes.get(block_id)
                    material_id = volume.material_id if volume is not None else None
                    element_rows.append({
                        "cell_id": int(cell_id),
                        "connectivity": cell_rows[cell_id] if cell_id < len(cell_rows) else [],
                        "cell_type": cell_types[cell_id] if cell_id < len(cell_types) else self.mesh_model.mesh_settings.element_family,
                        "volume_id": block_id,
                        "material_id": material_id,
                    })
            else:
                element_rows = []
                for cell_id, volume_id in enumerate(sorted(active_volume_ids)):
                    volume = self.geometry_model.volumes.get(volume_id)
                    element_rows.append({
                        "cell_id": int(cell_id),
                        "connectivity": [],
                        "cell_type": "volume_placeholder",
                        "volume_id": volume_id,
                        "material_id": None if volume is None else volume.material_id,
                    })

            active_bcs = [bc for bc in self.solver_model.boundary_conditions.values() if not bc.stage_ids or phase_id in bc.stage_ids]
            active_loads = [load for load in self.solver_model.loads.values() if (not load.stage_ids or phase_id in load.stage_ids or load.id in snapshot.active_load_ids)]
            active_interfaces = [self.structure_model.structural_interfaces[iid] for iid in snapshot.active_interface_ids if iid in self.structure_model.structural_interfaces]
            if not active_interfaces:
                active_interfaces = [row for row in self.structure_model.structural_interfaces.values() if not row.active_stage_ids or phase_id in row.active_stage_ids]
            used_material_ids = sorted({str(row.get("material_id")) for row in element_rows if row.get("material_id")} | {str(row.material_id) for row in active_interfaces if row.material_id})
            material_rows = [all_materials[mid].to_dict() if mid in all_materials else {"id": mid, "missing": True} for mid in used_material_ids]
            active_structures = [record for record in self.iter_structure_records() if (not record.active_stage_ids or phase_id in record.active_stage_ids or record.id in snapshot.active_structure_ids)]

            node_count = len(node_rows)
            active_dof_count = node_count * 3 if node_count else max(len(active_cell_ids), 1) * 3
            compiled = CompiledPhaseModel(
                id=f"compiled_{phase_id}",
                phase_id=phase_id,
                active_cell_count=int(len(active_cell_ids)),
                active_dof_count=int(active_dof_count),
                material_state_count=int(max(len(active_cell_ids), 1)),
                interface_count=len(active_interfaces),
                mesh_block={
                    "node_coordinates": node_rows,
                    "active_cell_ids": [int(v) for v in active_cell_ids],
                    "entity_map": self.mesh_model.mesh_entity_map.to_dict(),
                    "mesh_settings": self.mesh_model.mesh_settings.to_dict(),
                    "source": "MeshModel.MeshDocument" if mesh is not None else "GeometryModel.Volumes",
                },
                element_block={
                    "elements": element_rows,
                    "element_family": self.mesh_model.mesh_settings.element_family,
                    "active_volume_ids": sorted(active_volume_ids),
                },
                material_block={
                    "materials": material_rows,
                    "used_material_ids": used_material_ids,
                    "state_location": "cell_integration_points",
                },
                boundary_block={
                    "boundary_conditions": [bc.to_dict() for bc in active_bcs],
                    "dof_table": {"dofs_per_node": 3, "total_dofs": int(active_dof_count), "convention": ["ux", "uy", "uz"]},
                },
                load_block={
                    "loads": [load.to_dict() for load in active_loads],
                    "active_load_ids": [load.id for load in active_loads],
                },
                interface_block={
                    "interfaces": [row.to_dict() for row in active_interfaces],
                    "active_interface_ids": [row.id for row in active_interfaces],
                },
                state_variable_block={
                    "cell_state_variables": {"count": int(max(len(active_cell_ids), 1)), "variables": ["stress", "strain", "plastic_strain", "hardening"]},
                    "interface_state_variables": {"count": len(active_interfaces), "variables": ["normal_gap", "tangential_slip", "contact_status"]},
                    "water_condition_id": snapshot.water_condition_id,
                },
                solver_control_block={
                    "runtime_settings": self.solver_model.runtime_settings.to_dict(),
                    "calculation_settings": self.phase_manager.calculation_settings.get(phase_id, CalculationSettings()).to_dict(),
                },
                result_request_block={
                    "nodal_fields": ["ux", "uy", "uz"],
                    "cell_fields": ["stress", "strain", "plastic_point"],
                    "structure_outputs": ["axial_force", "bending_moment", "shear_force"],
                    "sections": [section.to_dict() for section in self.result_store.sections.values()],
                },
                metadata={
                    "backend": self.solver_model.runtime_settings.backend,
                    "contract": "compiled_phase_model_input_skeleton_v2",
                    "active_structure_ids": [record.id for record in active_structures],
                    "solid_cell_count": int(len(active_cell_ids)),
                    "surface_cell_count": int(len(surface_cell_ids)),
                    "skipped_surface_cell_ids": [int(v) for v in surface_cell_ids],
                    "solid_cell_gate": "tri3/quad4 surface cells are excluded from 3D solid element assembly",
                },
            )
            self.solver_model.compiled_phase_models[compiled.id] = compiled
        self.mark_changed(["solver"], action="compile_phase_models", affected_entities=list(self.solver_model.compiled_phase_models))
        try:
            from geoai_simkit.geoproject.transaction import get_invalidation_graph

            get_invalidation_graph(self).mark_clean("compiled_phase_models")
        except Exception:
            pass
        return self.solver_model.compiled_phase_models

    def framework_tree(self) -> dict[str, Any]:
        return {
            "GeoProjectDocument": {
                "ProjectSettings": self.project_settings.name,
                "SoilModel": ["SoilContour", "Boreholes", "SoilLayerSurfaces", "SoilClusters", "WaterConditions"],
                "GeometryModel": ["Points", "Curves", "Surfaces", "Volumes", "ParametricFeatures"],
                "TopologyGraph": ["ownership relations", "adjacency relations", "contact/interface candidates", "generated-by relations"],
                "StructureModel": ["Plates", "Beams", "EmbeddedBeams", "Anchors", "StructuralInterfaces"],
                "MaterialLibrary": ["SoilMaterials", "PlateMaterials", "BeamMaterials", "InterfaceMaterials", "Drainage / groundwater properties"],
                "MeshModel": ["MeshSettings", "MeshDocument", "MeshEntityMap", "QualityReport"],
                "PhaseManager": ["InitialPhase", "ConstructionPhases", "CalculationSettings", "PhaseStateSnapshots"],
                "SolverModel": ["CompiledPhaseModels", "BoundaryConditions", "Loads", "RuntimeSettings"],
                "ResultStore": ["PhaseResults", "EngineeringMetrics", "Curves", "Sections", "Reports"],
            }
        }

    def validate_framework(self) -> dict[str, Any]:
        material_ids = self.material_library.material_ids()
        missing_material_refs: list[str] = []
        for volume in self.geometry_model.volumes.values():
            if volume.material_id and volume.material_id not in material_ids:
                missing_material_refs.append(f"volume:{volume.id}->{volume.material_id}")
        for cluster in self.soil_model.soil_clusters.values():
            if cluster.material_id and cluster.material_id not in material_ids:
                missing_material_refs.append(f"cluster:{cluster.id}->{cluster.material_id}")
        phase_ids = {self.phase_manager.initial_phase.id, *self.phase_manager.construction_phases.keys()}
        snapshot_without_phase = [sid for sid in self.phase_manager.phase_state_snapshots if sid not in phase_ids]
        contact_edges = self.topology_graph.contact_edges()
        component_status = {
            "ProjectSettings": bool(self.project_settings.name),
            "SoilModel": self.soil_model.soil_contour is not None,
            "GeometryModel": True,
            "TopologyGraph": self.topology_graph is not None,
            "StructureModel": True,
            "MaterialLibrary": True,
            "MeshModel": self.mesh_model.mesh_settings is not None,
            "PhaseManager": self.phase_manager.initial_phase is not None,
            "SolverModel": self.solver_model.runtime_settings is not None,
            "ResultStore": self.result_store is not None,
        }
        return {
            "contract": CONTRACT_VERSION,
            "ok": all(component_status.values()) and not missing_material_refs and not snapshot_without_phase,
            "component_status": component_status,
            "counts": {
                "boreholes": len(self.soil_model.boreholes),
                "soil_clusters": len(self.soil_model.soil_clusters),
                "points": len(self.geometry_model.points),
                "curves": len(self.geometry_model.curves),
                "surfaces": len(self.geometry_model.surfaces),
                "volumes": len(self.geometry_model.volumes),
                "topology_nodes": len(self.topology_graph.nodes),
                "topology_edges": len(self.topology_graph.edges),
                "contact_candidates": len(contact_edges),
                "plates": len(self.structure_model.plates),
                "beams": len(self.structure_model.beams),
                "anchors": len(self.structure_model.anchors),
                "materials": len(material_ids),
                "mesh_nodes": self.mesh_model.mesh_document.node_count if self.mesh_model.mesh_document is not None else 0,
                "mesh_cells": self.mesh_model.mesh_document.cell_count if self.mesh_model.mesh_document is not None else 0,
                "phases": 1 + len(self.phase_manager.construction_phases),
                "compiled_phase_models": len(self.solver_model.compiled_phase_models),
                "phase_results": len(self.result_store.phase_results),
                "engineering_metrics": len(self.result_store.engineering_metrics),
            },
            "missing_material_refs": missing_material_refs,
            "snapshot_without_phase": snapshot_without_phase,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CONTRACT_VERSION,
            "ProjectSettings": self.project_settings.to_dict(),
            "SoilModel": self.soil_model.to_dict(),
            "GeometryModel": self.geometry_model.to_dict(),
            "TopologyGraph": self.topology_graph.to_dict(),
            "StructureModel": self.structure_model.to_dict(),
            "MaterialLibrary": self.material_library.to_dict(),
            "MeshModel": self.mesh_model.to_dict(),
            "PhaseManager": self.phase_manager.to_dict(),
            "SolverModel": self.solver_model.to_dict(),
            "ResultStore": self.result_store.to_dict(),
            "metadata": _jsonable_metadata(self.metadata),
        }


def _jsonable_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        if hasattr(value, "to_dict"):
            out[str(key)] = value.to_dict()
        else:
            out[str(key)] = value
    return out


def _safe_id(name: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in str(name).strip()]
    out = "".join(chars).strip("_") or "geo_project"
    while "__" in out:
        out = out.replace("__", "_")
    return out


def _infer_soil_model_from_geometry(geometry: GeometryDocument) -> SoilModel:
    bounds_rows = [block.bounds for block in geometry.blocks.values()]
    if bounds_rows:
        xmin = min(b[0] for b in bounds_rows)
        xmax = max(b[1] for b in bounds_rows)
        ymin = min(b[2] for b in bounds_rows)
        ymax = max(b[3] for b in bounds_rows)
        zmin = min(b[4] for b in bounds_rows)
        zmax = max(b[5] for b in bounds_rows)
    else:
        xmin, xmax, ymin, ymax, zmin, zmax = -10.0, 10.0, -5.0, 5.0, -20.0, 0.0
    contour = SoilContour(
        polygon=[(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)],
        z_top=zmax,
        z_bottom=zmin,
        metadata={"source": "geometry_bounds"},
    )
    model = SoilModel(soil_contour=contour, metadata={"source": "geometry_inference"})
    material_to_volumes: dict[str, list[str]] = {}
    for block in geometry.blocks.values():
        if block.role not in {"soil", "excavation", "rock"}:
            continue
        material_id = block.material_id or block.layer_id or "soil"
        material_to_volumes.setdefault(material_id, []).append(block.id)
    for material_id, volume_ids in material_to_volumes.items():
        model.add_cluster(SoilCluster(id=f"cluster_{material_id}", name=f"Cluster {material_id}", volume_ids=volume_ids, material_id=material_id, layer_id=material_id, metadata={"source": "geometry_roles"}))
    model.add_water_condition(WaterCondition(id="global_phreatic_level", name="Global phreatic level", level=0.0, target_ids=list(model.soil_clusters), metadata={"source": "default"}))
    return model


def _infer_structure_model(document: Any) -> StructureModel:
    model = StructureModel(metadata={"source": "geometry_roles_and_engineering_document"})
    for block in document.geometry.blocks.values():
        if block.role == "wall":
            model.add_plate(StructureRecord(id=f"plate_{block.id}", name=f"Plate {block.name}", geometry_ref=block.id, material_id=block.material_id or "wall_plate", active_stage_ids=list(block.active_stage_ids), metadata={"source": "wall_volume", "bounds": list(block.bounds)}))
        elif block.role in {"support", "structure"}:
            model.add_beam(StructureRecord(id=f"beam_{block.id}", name=f"Beam {block.name}", geometry_ref=block.id, material_id=block.material_id or "support_beam", active_stage_ids=list(block.active_stage_ids), metadata={"source": "support_volume", "bounds": list(block.bounds)}))
    for key, row in dict(getattr(document, "supports", {}) or {}).items():
        record = StructureRecord.from_dict({"id": str(key), "name": str(key), **_as_dict(row)})
        model.add_beam(record)
    for key, row in dict(getattr(document, "interfaces", {}) or {}).items():
        payload = {"id": str(key), "name": str(key), **_as_dict(row)}
        model.add_interface(StructuralInterfaceRecord.from_dict(payload))
    return model


def _infer_material_library(document: Any, soil: SoilModel, structures: StructureModel) -> MaterialLibrary:
    library = MaterialLibrary(metadata={"source": "EngineeringDocument"})
    for material_id, record in dict(getattr(document, "materials", {}) or {}).items():
        mat = MaterialRecord(id=str(material_id), name=str(getattr(record, "name", material_id)), model_type=str(getattr(record, "model_type", "engineering_placeholder")), parameters=dict(getattr(record, "parameters", {}) or {}), metadata=dict(getattr(record, "metadata", {}) or {}))
        library.soil_materials[mat.id] = mat
    for cluster in soil.soil_clusters.values():
        if cluster.material_id not in library.soil_materials:
            library.soil_materials[cluster.material_id] = MaterialRecord(id=cluster.material_id, name=cluster.material_id, model_type="mohr_coulomb_placeholder", drainage=cluster.drainage, parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0}, metadata={"source": "soil_cluster_default"})
    for plate in structures.plates.values():
        if plate.material_id and plate.material_id not in library.plate_materials:
            library.plate_materials[plate.material_id] = MaterialRecord(id=plate.material_id, name=plate.material_id, model_type="elastic_plate", parameters={"EA": 1.0e7, "EI": 1.0e5}, metadata={"source": "structure_default"})
    for beam in structures.beams.values():
        if beam.material_id and beam.material_id not in library.beam_materials:
            library.beam_materials[beam.material_id] = MaterialRecord(id=beam.material_id, name=beam.material_id, model_type="elastic_beam", parameters={"EA": 1.0e6}, metadata={"source": "structure_default"})
    for interface in structures.structural_interfaces.values():
        material_id = interface.material_id or f"mat_{interface.id}"
        interface.material_id = material_id
        if material_id not in library.interface_materials:
            library.interface_materials[material_id] = MaterialRecord(id=material_id, name=material_id, model_type="interface_frictional", parameters={"R_inter": 0.67}, metadata={"source": "interface_default"})
    library.drainage_groundwater_properties["default_drainage"] = DrainageGroundwaterProperty(id="default_drainage", name="Default drainage", metadata={"source": "default"})
    return library


def _topology_from_dict(data: Mapping[str, Any] | None) -> TopologyGraph:
    from geoai_simkit.geometry.topology_graph import TopologyEdge, TopologyNode

    data = dict(data or {})
    graph = TopologyGraph()
    for row in list(data.get("nodes", []) or []):
        row = dict(row)
        node_id = str(row.get("id", "node"))
        graph.nodes[node_id] = TopologyNode(id=node_id, type=str(row.get("type", "block")), label=str(row.get("label", node_id)), attributes=dict(row.get("attributes", {}) or {}))  # type: ignore[arg-type]
    for row in list(data.get("edges", []) or []):
        row = dict(row)
        graph.edges.append(TopologyEdge(source=str(row.get("source", "")), target=str(row.get("target", "")), relation=str(row.get("relation", "connected_to")), attributes=dict(row.get("attributes", {}) or {})))  # type: ignore[arg-type]
    return graph


__all__ = [
    "CONTRACT_VERSION",
    "ProjectSettings",
    "SoilContour",
    "BoreholeLayer",
    "Borehole",
    "SoilLayerSurface",
    "SoilCluster",
    "WaterCondition",
    "SoilModel",
    "GeometryCurve",
    "GeometrySurface",
    "GeometryVolume",
    "GeometryModel",
    "StructureRecord",
    "AnchorRecord",
    "StructuralInterfaceRecord",
    "StructureModel",
    "MaterialRecord",
    "DrainageGroundwaterProperty",
    "MaterialLibrary",
    "MeshSettings",
    "MeshModel",
    "CalculationSettings",
    "PhaseStateSnapshot",
    "PhaseManager",
    "BoundaryCondition",
    "LoadRecord",
    "RuntimeSettings",
    "CompiledPhaseModel",
    "SolverModel",
    "EngineeringMetricRecord",
    "ResultCurve",
    "ResultSection",
    "ReportReference",
    "ResultStore",
    "GeoProjectDocument",
]
