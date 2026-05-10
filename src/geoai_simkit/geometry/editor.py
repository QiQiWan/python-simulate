from __future__ import annotations

"""Dependency-light point/line/surface/block editing service.

The editor is the geometry side of the modern visual modeling workbench. It is
not a CAD kernel; it creates stable engineering entities that can later be
converted to OCC/PyVista/gmsh objects while preserving semantic IDs.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from geoai_simkit.geometry.entities import BlockEntity, EdgeEntity, FaceEntity, PointEntity, SurfaceEntity
from geoai_simkit.geometry.kernel import GeometryDocument


@dataclass(slots=True)
class GeometryLocator:
    grid_size: float = 1.0
    snap_tolerance: float = 0.25
    plane: str = "xz"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)

    def snap(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        gx = self.grid_size if self.grid_size > 0 else 1.0
        return tuple(round(float(v) / gx) * gx for v in point)  # type: ignore[return-value]

    def locate(self, x: float, y: float, z: float, *, snap: bool = True) -> dict[str, Any]:
        raw = (float(x), float(y), float(z))
        located = self.snap(raw) if snap else raw
        return {
            "raw": list(raw),
            "snapped": list(located),
            "grid_size": float(self.grid_size),
            "snap_enabled": bool(snap),
            "plane": self.plane,
            "origin": list(self.origin),
        }


def _next_id(existing: dict[str, Any], prefix: str) -> str:
    index = len(existing) + 1
    while f"{prefix}_{index:03d}" in existing:
        index += 1
    return f"{prefix}_{index:03d}"


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


class GeometryEditor:
    def __init__(self, document: GeometryDocument, *, locator: GeometryLocator | None = None) -> None:
        self.document = document
        self.locator = locator or GeometryLocator()

    def find_nearest_point(self, xyz: tuple[float, float, float], *, tolerance: float | None = None) -> PointEntity | None:
        tol = self.locator.snap_tolerance if tolerance is None else float(tolerance)
        nearest: tuple[float, PointEntity] | None = None
        for point in self.document.points.values():
            d = _distance(point.to_tuple(), xyz)
            if d <= tol and (nearest is None or d < nearest[0]):
                nearest = (d, point)
        return None if nearest is None else nearest[1]

    def create_point(
        self,
        x: float,
        y: float,
        z: float,
        *,
        point_id: str | None = None,
        snap: bool = True,
        reuse_existing: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> PointEntity:
        located = self.locator.locate(x, y, z, snap=snap)
        xyz = tuple(float(v) for v in located["snapped"])
        if reuse_existing:
            existing = self.find_nearest_point(xyz)
            if existing is not None:
                return existing
        pid = point_id or _next_id(self.document.points, "pt")
        if pid in self.document.points:
            raise ValueError(f"Point already exists: {pid}")
        point = PointEntity(id=pid, x=xyz[0], y=xyz[1], z=xyz[2], metadata={"located": located, **dict(metadata or {})})
        self.document.points[pid] = point
        self.document.metadata["last_geometry_edit"] = f"create_point:{pid}"
        return point

    def move_point(self, point_id: str, x: float, y: float, z: float, *, snap: bool = True) -> tuple[PointEntity, tuple[float, float, float]]:
        if point_id not in self.document.points:
            raise KeyError(f"Point not found: {point_id}")
        point = self.document.points[point_id]
        previous = point.to_tuple()
        located = self.locator.locate(x, y, z, snap=snap)
        xyz = tuple(float(v) for v in located["snapped"])
        point.x, point.y, point.z = xyz
        point.metadata["last_move"] = {"from": list(previous), "to": list(xyz), "located": located}
        self.document.metadata["last_geometry_edit"] = f"move_point:{point_id}"
        return point, previous

    def create_edge(
        self,
        point_ids: list[str] | tuple[str, ...],
        *,
        edge_id: str | None = None,
        role: str = "sketch",
        closed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> EdgeEntity:
        ids = tuple(str(v) for v in point_ids)
        if len(ids) < 2:
            raise ValueError("An edge/polyline requires at least two points.")
        missing = [pid for pid in ids if pid not in self.document.points]
        if missing:
            raise KeyError(f"Edge references missing points: {missing}")
        eid = edge_id or _next_id(self.document.edges, "edge")
        if eid in self.document.edges:
            raise ValueError(f"Edge already exists: {eid}")
        edge = EdgeEntity(id=eid, point_ids=ids, role=role, closed=bool(closed), metadata=dict(metadata or {}))
        self.document.edges[eid] = edge
        self.document.metadata["last_geometry_edit"] = f"create_edge:{eid}"
        return edge

    def create_line_from_coords(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        *,
        edge_id: str | None = None,
        role: str = "sketch",
        snap: bool = True,
    ) -> EdgeEntity:
        p1 = self.create_point(*start, snap=snap, reuse_existing=True, metadata={"created_by": "line_start"})
        p2 = self.create_point(*end, snap=snap, reuse_existing=True, metadata={"created_by": "line_end"})
        return self.create_edge((p1.id, p2.id), edge_id=edge_id, role=role)

    def create_surface(
        self,
        point_ids: list[str] | tuple[str, ...],
        *,
        surface_id: str | None = None,
        role: str = "sketch",
        plane: str = "xz",
        metadata: dict[str, Any] | None = None,
    ) -> SurfaceEntity:
        ids = tuple(str(v) for v in point_ids)
        if len(ids) < 3:
            raise ValueError("A surface requires at least three points.")
        missing = [pid for pid in ids if pid not in self.document.points]
        if missing:
            raise KeyError(f"Surface references missing points: {missing}")
        sid = surface_id or _next_id(self.document.surfaces, "surf")
        if sid in self.document.surfaces:
            raise ValueError(f"Surface already exists: {sid}")
        outer_edge_id = f"edge_{sid}_outer"
        if outer_edge_id not in self.document.edges:
            self.create_edge(ids + (ids[0],), edge_id=outer_edge_id, role="boundary", closed=True, metadata={"surface_id": sid})
        surface = SurfaceEntity(id=sid, outer_edge_id=outer_edge_id, point_ids=ids, role=role, plane=plane, metadata=dict(metadata or {}))
        self.document.surfaces[sid] = surface
        self.document.metadata["last_geometry_edit"] = f"create_surface:{sid}"
        return surface

    def create_surface_from_coords(
        self,
        coords: list[tuple[float, float, float]] | tuple[tuple[float, float, float], ...],
        *,
        surface_id: str | None = None,
        role: str = "sketch",
        plane: str = "xz",
        snap: bool = True,
    ) -> SurfaceEntity:
        point_ids = [self.create_point(*xyz, snap=snap, reuse_existing=True, metadata={"created_by": "surface"}).id for xyz in coords]
        return self.create_surface(point_ids, surface_id=surface_id, role=role, plane=plane)

    def create_block(
        self,
        bounds: tuple[float, float, float, float, float, float],
        *,
        block_id: str | None = None,
        name: str | None = None,
        role: str = "structure",
        material_id: str | None = None,
        layer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BlockEntity:
        xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]
        if xmax <= xmin or ymax <= ymin or zmax <= zmin:
            raise ValueError(f"Invalid block bounds: {bounds}")
        bid = block_id or _next_id(self.document.blocks, "block")
        if bid in self.document.blocks:
            raise ValueError(f"Block already exists: {bid}")
        face_ids: list[str] = []
        face_specs = [
            ("x", "min", xmin, (ymax - ymin) * (zmax - zmin), (-1.0, 0.0, 0.0)),
            ("x", "max", xmax, (ymax - ymin) * (zmax - zmin), (1.0, 0.0, 0.0)),
            ("y", "min", ymin, (xmax - xmin) * (zmax - zmin), (0.0, -1.0, 0.0)),
            ("y", "max", ymax, (xmax - xmin) * (zmax - zmin), (0.0, 1.0, 0.0)),
            ("z", "min", zmin, (xmax - xmin) * (ymax - ymin), (0.0, 0.0, -1.0)),
            ("z", "max", zmax, (xmax - xmin) * (ymax - ymin), (0.0, 0.0, 1.0)),
        ]
        for axis, side, coordinate, area, normal in face_specs:
            fid = f"face:{bid}:{axis}_{side}"
            self.document.faces[fid] = FaceEntity(
                id=fid,
                owner_block_id=bid,
                axis=axis,
                side=side,
                coordinate=coordinate,
                area=area,
                boundary_type="external",
                normal=normal,
                metadata={"created_by": "GeometryEditor.create_block"},
            )
            face_ids.append(fid)
        block = BlockEntity(
            id=bid,
            name=name or bid,
            bounds=(xmin, xmax, ymin, ymax, zmin, zmax),
            role=role,  # type: ignore[arg-type]
            material_id=material_id,
            layer_id=layer_id,
            face_ids=tuple(face_ids),
            metadata={"created_by": "GeometryEditor.create_block", **dict(metadata or {})},
        )
        self.document.blocks[bid] = block
        self.document.metadata["last_geometry_edit"] = f"create_block:{bid}"
        return block

    def delete_entity(self, entity_type: str, entity_id: str) -> Any | None:
        stores = {
            "point": self.document.points,
            "edge": self.document.edges,
            "surface": self.document.surfaces,
            "block": self.document.blocks,
            "face": self.document.faces,
        }
        store = stores.get(entity_type)
        if store is None:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        value = store.pop(entity_id, None)
        self.document.metadata["last_geometry_edit"] = f"delete_{entity_type}:{entity_id}"
        return value

    def contract(self) -> dict[str, Any]:
        return {
            "locator": {
                "grid_size": self.locator.grid_size,
                "snap_tolerance": self.locator.snap_tolerance,
                "plane": self.locator.plane,
                "origin": list(self.locator.origin),
            },
            "counts": {
                "points": len(self.document.points),
                "edges": len(self.document.edges),
                "surfaces": len(self.document.surfaces),
                "blocks": len(self.document.blocks),
                "faces": len(self.document.faces),
            },
            "available_tools": ["select", "point", "line", "surface", "block_box", "move_point", "box_select", "multi_select", "context_menu"],
        }


__all__ = ["GeometryLocator", "GeometryEditor"]
