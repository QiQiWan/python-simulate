from __future__ import annotations

"""Undoable commands for direct interactive 3D geometry editing.

The commands in this module are intentionally dependency-light.  They mutate the
GeoProjectDocument geometry model directly and keep full document snapshots for
robust undo/redo during GUI operations.  The implementation favours predictable
engineering editing behaviour over CAD-kernel completeness: axis-aligned blocks,
raw point topology and surface extrusion are supported now; boolean operations
produce auditable feature records that native OCC/Gmsh backends can consume later.
"""

from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Any, Iterable

from geoai_simkit.commands.command import Command, CommandResult


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "geometry_model") and hasattr(document, "to_dict")


def _restore_document(document: Any, backup: dict[str, Any] | None) -> None:
    if backup is None:
        return
    restored = document.__class__.from_dict(backup)
    for field_name in document.__dataclass_fields__:
        setattr(document, field_name, getattr(restored, field_name))


def _mark(document: Any, action: str, affected: list[str]) -> None:
    if hasattr(document, "mark_changed"):
        try:
            document.mark_changed(["geometry", "topology", "mesh", "solver", "result"], action=action, affected_entities=affected)
        except Exception:
            pass


def _next_id(prefix: str, existing: dict[str, Any]) -> str:
    index = len(existing) + 1
    while f"{prefix}_{index:03d}" in existing:
        index += 1
    return f"{prefix}_{index:03d}"


def _entity_store(document: Any, entity_id: str, entity_type: str | None = None) -> tuple[str, Any | None]:
    model = document.geometry_model
    normalized = (entity_type or "").lower()
    stores = [
        ("point", model.points),
        ("curve", model.curves),
        ("edge", model.curves),
        ("surface", model.surfaces),
        ("volume", model.volumes),
        ("block", model.volumes),
    ]
    if normalized:
        for kind, store in stores:
            if kind == normalized and entity_id in store:
                return kind, store[entity_id]
    for kind, store in stores:
        if entity_id in store:
            return kind, store[entity_id]
    return normalized or "unknown", None


def _point_ids_for_entity(document: Any, entity_id: str, entity_type: str | None = None) -> list[str]:
    kind, entity = _entity_store(document, entity_id, entity_type)
    if entity is None:
        return []
    if kind == "point":
        return [entity_id]
    if kind in {"curve", "edge"}:
        return list(getattr(entity, "point_ids", []) or [])
    if kind == "surface":
        return list(getattr(entity, "point_ids", []) or [])
    if kind in {"volume", "block"}:
        # Axis-aligned volume bounds are transformed through the bounds rather
        # than point topology, because GeoProject volumes are not required to
        # own corner PointEntity objects.
        return []
    return []


def _move_volume_bounds(bounds: Iterable[float], dx: float, dy: float, dz: float) -> tuple[float, float, float, float, float, float]:
    x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
    return (x0 + dx, x1 + dx, y0 + dy, y1 + dy, z0 + dz, z1 + dz)


def _scale_volume_bounds(bounds: Iterable[float], sx: float, sy: float, sz: float, origin: tuple[float, float, float]) -> tuple[float, float, float, float, float, float]:
    x0, x1, y0, y1, z0, z1 = [float(v) for v in bounds]
    ox, oy, oz = origin
    pts = [(x0, y0, z0), (x1, y1, z1)]
    out = [((x - ox) * sx + ox, (y - oy) * sy + oy, (z - oz) * sz + oz) for x, y, z in pts]
    xs, ys, zs = zip(*out)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _rotate_xy(x: float, y: float, angle_deg: float, origin: tuple[float, float, float]) -> tuple[float, float]:
    ox, oy, _oz = origin
    theta = radians(float(angle_deg))
    c, s = cos(theta), sin(theta)
    rx, ry = x - ox, y - oy
    return (ox + rx * c - ry * s, oy + rx * s + ry * c)


def _entity_bounds(document: Any, entity_id: str, entity_type: str | None = None) -> tuple[float, float, float, float, float, float] | None:
    kind, entity = _entity_store(document, entity_id, entity_type)
    if entity is None:
        return None
    if kind in {"volume", "block"}:
        return getattr(entity, "bounds", None)
    pts = []
    for pid in _point_ids_for_entity(document, entity_id, entity_type):
        point = document.geometry_model.points.get(pid)
        if point is not None:
            pts.append(point.to_tuple())
    if not pts:
        return None
    xs, ys, zs = zip(*pts)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _center(bounds: tuple[float, float, float, float, float, float] | None) -> tuple[float, float, float]:
    if bounds is None:
        return (0.0, 0.0, 0.0)
    return ((bounds[0] + bounds[1]) * 0.5, (bounds[2] + bounds[3]) * 0.5, (bounds[4] + bounds[5]) * 0.5)


@dataclass(slots=True)
class TransformGeometryCommand(Command):
    entity_ids: tuple[str, ...]
    entity_type: str = ""
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotate_z_deg: float = 0.0
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    origin: tuple[float, float, float] | None = None
    id: str = "transform_geometry"
    name: str = "Transform geometry"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Transform requires GeoProjectDocument")
        self._backup = document.to_dict()
        affected: set[str] = set()
        dx, dy, dz = [float(v) for v in self.translate]
        sx, sy, sz = [float(v) for v in self.scale]
        origin = self.origin or _center(_entity_bounds(document, self.entity_ids[0], self.entity_type) if self.entity_ids else None)
        for entity_id in self.entity_ids:
            kind, entity = _entity_store(document, entity_id, self.entity_type)
            if entity is None:
                continue
            if kind in {"volume", "block"} and getattr(entity, "bounds", None) is not None:
                bounds = _scale_volume_bounds(entity.bounds, sx, sy, sz, origin)
                if abs(float(self.rotate_z_deg)) > 1e-12:
                    x0, x1, y0, y1, z0, z1 = bounds
                    corners = [
                        _rotate_xy(x, y, self.rotate_z_deg, origin)
                        for x in (x0, x1)
                        for y in (y0, y1)
                    ]
                    xs, ys = zip(*corners)
                    bounds = (min(xs), max(xs), min(ys), max(ys), z0, z1)
                entity.bounds = _move_volume_bounds(bounds, dx, dy, dz)
                entity.metadata["last_transform"] = {"translate": list(self.translate), "rotate_z_deg": float(self.rotate_z_deg), "scale": list(self.scale), "origin": list(origin)}
                affected.add(entity_id)
            else:
                for pid in _point_ids_for_entity(document, entity_id, self.entity_type):
                    point = document.geometry_model.points.get(pid)
                    if point is None:
                        continue
                    x = (point.x - origin[0]) * sx + origin[0]
                    y = (point.y - origin[1]) * sy + origin[1]
                    z = (point.z - origin[2]) * sz + origin[2]
                    if abs(float(self.rotate_z_deg)) > 1e-12:
                        x, y = _rotate_xy(x, y, self.rotate_z_deg, origin)
                    point.x, point.y, point.z = x + dx, y + dy, z + dz
                    affected.add(pid)
                affected.add(entity_id)
        _mark(document, self.id, sorted(affected))
        return CommandResult(self.id, self.name, ok=True, affected_entities=sorted(affected), message=f"Transformed {len(self.entity_ids)} entity(ies)", metadata={"translate": list(self.translate), "rotate_z_deg": float(self.rotate_z_deg), "scale": list(self.scale)})

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=list(self.entity_ids))


@dataclass(slots=True)
class CopyGeometryCommand(Command):
    entity_ids: tuple[str, ...]
    entity_type: str = ""
    offset: tuple[float, float, float] = (1.0, 0.0, 0.0)
    id: str = "copy_geometry"
    name: str = "Copy geometry"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _created_ids: list[str] = field(default_factory=list, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Copy requires GeoProjectDocument")
        import copy
        from geoai_simkit.geometry.entities import PointEntity
        from geoai_simkit.geoproject import GeometryCurve, GeometrySurface, GeometryVolume

        self._backup = document.to_dict()
        dx, dy, dz = [float(v) for v in self.offset]
        created: list[str] = []
        for entity_id in self.entity_ids:
            kind, entity = _entity_store(document, entity_id, self.entity_type)
            if entity is None:
                continue
            point_map: dict[str, str] = {}
            def clone_point(pid: str) -> str:
                if pid in point_map:
                    return point_map[pid]
                p = document.geometry_model.points[pid]
                new_pid = _next_id("point", document.geometry_model.points)
                document.geometry_model.points[new_pid] = PointEntity(new_pid, p.x + dx, p.y + dy, p.z + dz, metadata={**dict(p.metadata), "copied_from": pid})
                point_map[pid] = new_pid
                created.append(new_pid)
                return new_pid
            if kind == "point":
                clone_point(entity_id)
            elif kind in {"curve", "edge"}:
                new_id = _next_id("curve", document.geometry_model.curves)
                new_points = [clone_point(pid) for pid in entity.point_ids]
                document.geometry_model.curves[new_id] = GeometryCurve(new_id, f"{entity.name}_copy", new_points, kind=entity.kind, metadata={**dict(entity.metadata), "copied_from": entity.id})
                created.append(new_id)
            elif kind == "surface":
                new_id = _next_id("surface", document.geometry_model.surfaces)
                new_points = [clone_point(pid) for pid in entity.point_ids]
                document.geometry_model.surfaces[new_id] = GeometrySurface(new_id, f"{entity.name}_copy", new_points, kind=entity.kind, metadata={**dict(entity.metadata), "copied_from": entity.id})
                created.append(new_id)
            elif kind in {"volume", "block"} and entity.bounds is not None:
                new_id = _next_id("volume", document.geometry_model.volumes)
                new_volume = GeometryVolume(new_id, f"{entity.name}_copy", bounds=_move_volume_bounds(entity.bounds, dx, dy, dz), surface_ids=list(entity.surface_ids), role=entity.role, material_id=entity.material_id, metadata={**dict(entity.metadata), "copied_from": entity.id})
                document.geometry_model.volumes[new_id] = new_volume
                for phase_id in document.phase_ids():
                    try:
                        document.set_phase_volume_activation(phase_id, new_id, True)
                    except Exception:
                        pass
                created.append(new_id)
        self._created_ids = created
        _mark(document, self.id, created)
        return CommandResult(self.id, self.name, ok=True, affected_entities=created, message=f"Copied {len(self.entity_ids)} entity(ies)", metadata={"created_ids": created})

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=list(self._created_ids))


@dataclass(slots=True)
class ExtrudeSurfaceCommand(Command):
    surface_id: str
    vector: tuple[float, float, float] = (0.0, 0.0, -5.0)
    role: str = "structure"
    material_id: str | None = None
    id: str = "extrude_surface"
    name: str = "Extrude surface to volume"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _created_id: str = field(default="", init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document) or self.surface_id not in document.geometry_model.surfaces:
            return CommandResult(self.id, self.name, ok=False, message=f"Surface not found: {self.surface_id}")
        from geoai_simkit.geoproject import GeometryVolume
        self._backup = document.to_dict()
        surface = document.geometry_model.surfaces[self.surface_id]
        pts = [document.geometry_model.points[pid].to_tuple() for pid in surface.point_ids if pid in document.geometry_model.points]
        if len(pts) < 3:
            return CommandResult(self.id, self.name, ok=False, message="Surface extrusion requires at least 3 points")
        dx, dy, dz = [float(v) for v in self.vector]
        all_pts = [*pts, *[(x + dx, y + dy, z + dz) for x, y, z in pts]]
        xs, ys, zs = zip(*all_pts)
        vid = _next_id("volume", document.geometry_model.volumes)
        volume = GeometryVolume(vid, f"extrude_{self.surface_id}", bounds=(min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)), surface_ids=[self.surface_id], role=self.role, material_id=self.material_id, metadata={"created_by_command": self.id, "source_surface_id": self.surface_id, "extrude_vector": list(self.vector), "visible": True})
        document.geometry_model.volumes[vid] = volume
        for phase_id in document.phase_ids():
            try:
                document.set_phase_volume_activation(phase_id, vid, True)
            except Exception:
                pass
        self._created_id = vid
        _mark(document, self.id, [self.surface_id, vid])
        return CommandResult(self.id, self.name, ok=True, affected_entities=[self.surface_id, vid], message=f"Extruded {self.surface_id} to {vid}", metadata=volume.to_dict())

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self.surface_id, self._created_id])


@dataclass(slots=True)
class CutVolumeCommand(Command):
    volume_id: str
    axis: str = "z"
    coordinate: float = 0.0
    id: str = "cut_volume"
    name: str = "Cut volume by axis plane"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _created_ids: list[str] = field(default_factory=list, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document) or self.volume_id not in document.geometry_model.volumes:
            return CommandResult(self.id, self.name, ok=False, message=f"Volume not found: {self.volume_id}")
        from geoai_simkit.geoproject import GeometryVolume
        self._backup = document.to_dict()
        volume = document.geometry_model.volumes[self.volume_id]
        if volume.bounds is None:
            return CommandResult(self.id, self.name, ok=False, message="Volume has no axis-aligned bounds")
        x0, x1, y0, y1, z0, z1 = [float(v) for v in volume.bounds]
        axis = self.axis.lower()
        c = float(self.coordinate)
        if axis == "x" and x0 < c < x1:
            b1, b2 = (x0, c, y0, y1, z0, z1), (c, x1, y0, y1, z0, z1)
        elif axis == "y" and y0 < c < y1:
            b1, b2 = (x0, x1, y0, c, z0, z1), (x0, x1, c, y1, z0, z1)
        elif axis == "z" and z0 < c < z1:
            b1, b2 = (x0, x1, y0, y1, z0, c), (x0, x1, y0, y1, c, z1)
        else:
            return CommandResult(self.id, self.name, ok=False, message="Cut coordinate is outside volume bounds")
        document.geometry_model.volumes.pop(self.volume_id, None)
        ids = []
        for bounds in (b1, b2):
            vid = _next_id("volume", document.geometry_model.volumes)
            document.geometry_model.volumes[vid] = GeometryVolume(vid, f"{volume.name}_{axis}_cut", bounds=bounds, surface_ids=list(volume.surface_ids), role=volume.role, material_id=volume.material_id, metadata={**dict(volume.metadata), "cut_from": self.volume_id, "cut_axis": axis, "cut_coordinate": c})
            ids.append(vid)
            for phase_id in document.phase_ids():
                try:
                    document.set_phase_volume_activation(phase_id, vid, True)
                except Exception:
                    pass
        self._created_ids = ids
        _mark(document, self.id, [self.volume_id, *ids])
        return CommandResult(self.id, self.name, ok=True, affected_entities=[self.volume_id, *ids], message=f"Cut {self.volume_id} into {', '.join(ids)}", metadata={"created_ids": ids})

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self.volume_id, *self._created_ids])


@dataclass(slots=True)
class BooleanGeometryCommand(Command):
    operation: str
    target_ids: tuple[str, ...]
    id: str = "boolean_geometry"
    name: str = "Boolean geometry operation"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _feature_id: str = field(default="", init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Boolean operation requires GeoProjectDocument")
        from geoai_simkit.geometry.entities import PartitionFeature
        self._backup = document.to_dict()
        fid = _next_id("feature", document.geometry_model.parametric_features)
        operation = str(self.operation).lower()
        document.geometry_model.parametric_features[fid] = PartitionFeature(
            id=fid,
            type="manual_split",
            parameters={"operation": operation, "target_ids": list(self.target_ids), "backend": "deferred_occ_boolean"},
            target_block_ids=tuple(self.target_ids),
            generated_block_ids=(),
            metadata={"created_by_command": self.id, "status": "deferred", "message": "Boolean union/subtract recorded as auditable feature; native OCC execution can consume this feature."},
        )
        for tid in self.target_ids:
            kind, entity = _entity_store(document, tid, "volume")
            if entity is not None:
                entity.metadata.setdefault("boolean_features", []).append(fid)
        self._feature_id = fid
        _mark(document, self.id, [fid, *self.target_ids])
        return CommandResult(self.id, self.name, ok=True, affected_entities=[fid, *self.target_ids], message=f"Recorded boolean {operation} feature {fid}", metadata=document.geometry_model.parametric_features[fid].to_dict())

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self._feature_id, *self.target_ids])


@dataclass(slots=True)
class SetEntityCoordinatesCommand(Command):
    entity_id: str
    entity_type: str = "point"
    x: float | None = None
    y: float | None = None
    z: float | None = None
    width: float | None = None
    depth: float | None = None
    height: float | None = None
    id: str = "set_entity_coordinates"
    name: str = "Set entity coordinates/dimensions"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Coordinate editing requires GeoProjectDocument")
        self._backup = document.to_dict()
        kind, entity = _entity_store(document, self.entity_id, self.entity_type)
        if entity is None:
            return CommandResult(self.id, self.name, ok=False, message=f"Entity not found: {self.entity_type}:{self.entity_id}")
        if kind == "point":
            if self.x is not None: entity.x = float(self.x)
            if self.y is not None: entity.y = float(self.y)
            if self.z is not None: entity.z = float(self.z)
        elif kind in {"volume", "block"} and entity.bounds is not None:
            x0, x1, y0, y1, z0, z1 = [float(v) for v in entity.bounds]
            cx, cy, cz = _center(entity.bounds)
            if self.x is not None: cx = float(self.x)
            if self.y is not None: cy = float(self.y)
            if self.z is not None: cz = float(self.z)
            w = float(self.width if self.width is not None else max(x1 - x0, 0.0))
            d = float(self.depth if self.depth is not None else max(y1 - y0, 0.0))
            h = float(self.height if self.height is not None else max(z1 - z0, 0.0))
            entity.bounds = (cx - w * 0.5, cx + w * 0.5, cy - d * 0.5, cy + d * 0.5, cz - h * 0.5, cz + h * 0.5)
        else:
            # Curves/surfaces are positioned by translating their points so the
            # entity centroid matches the requested coordinates.
            bounds = _entity_bounds(document, self.entity_id, self.entity_type)
            cx, cy, cz = _center(bounds)
            dx = 0.0 if self.x is None else float(self.x) - cx
            dy = 0.0 if self.y is None else float(self.y) - cy
            dz = 0.0 if self.z is None else float(self.z) - cz
            for pid in _point_ids_for_entity(document, self.entity_id, self.entity_type):
                p = document.geometry_model.points.get(pid)
                if p is not None:
                    p.x, p.y, p.z = p.x + dx, p.y + dy, p.z + dz
        _mark(document, self.id, [self.entity_id])
        return CommandResult(self.id, self.name, ok=True, affected_entities=[self.entity_id], message=f"Updated coordinates for {self.entity_id}")

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self.entity_id])


__all__ = [
    "TransformGeometryCommand",
    "CopyGeometryCommand",
    "ExtrudeSurfaceCommand",
    "CutVolumeCommand",
    "BooleanGeometryCommand",
    "SetEntityCoordinatesCommand",
]
