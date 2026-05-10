from __future__ import annotations

"""Stable engineering geometry entities for visual FEM modeling.

These entities are deliberately lightweight. They describe what the GUI edits
and what the mesh/solver need to preserve, without requiring OpenCascade,
PyVista or a meshing backend at import time.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

BlockRole = Literal["soil", "excavation", "wall", "support", "structure", "void", "rock", "unknown"]
FaceBoundaryType = Literal[
    "internal",
    "external",
    "ground_surface",
    "bottom",
    "symmetry",
    "wall_contact",
    "excavation_boundary",
    "horizontal_layer",
    "unknown",
]
SurfaceRole = Literal["sketch", "partition", "boundary", "excavation", "interface", "unknown"]
EdgeRole = Literal["sketch", "axis", "boundary", "support_axis", "unknown"]


@dataclass(slots=True)
class PointEntity:
    id: str
    x: float
    y: float
    z: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_tuple(self) -> tuple[float, float, float]:
        return (float(self.x), float(self.y), float(self.z))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "x": float(self.x), "y": float(self.y), "z": float(self.z), "metadata": dict(self.metadata)}


@dataclass(slots=True)
class EdgeEntity:
    id: str
    point_ids: tuple[str, ...]
    role: EdgeRole = "sketch"
    closed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "point_ids": list(self.point_ids),
            "role": self.role,
            "closed": bool(self.closed),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class SurfaceEntity:
    id: str
    outer_edge_id: str | None = None
    point_ids: tuple[str, ...] = ()
    hole_edge_ids: tuple[str, ...] = ()
    role: SurfaceRole = "sketch"
    plane: str = "xz"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "outer_edge_id": self.outer_edge_id,
            "point_ids": list(self.point_ids),
            "hole_edge_ids": list(self.hole_edge_ids),
            "role": self.role,
            "plane": self.plane,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class FaceEntity:
    id: str
    owner_block_id: str
    axis: str = ""
    side: str = ""
    coordinate: float = 0.0
    area: float = 0.0
    boundary_type: FaceBoundaryType = "unknown"
    adjacent_block_id: str | None = None
    interface_id: str | None = None
    normal: tuple[float, float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_block_id": self.owner_block_id,
            "axis": self.axis,
            "side": self.side,
            "coordinate": float(self.coordinate),
            "area": float(self.area),
            "boundary_type": self.boundary_type,
            "adjacent_block_id": self.adjacent_block_id,
            "interface_id": self.interface_id,
            "normal": list(self.normal) if self.normal is not None else None,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class BlockEntity:
    id: str
    name: str
    bounds: tuple[float, float, float, float, float, float]
    role: BlockRole = "unknown"
    material_id: str | None = None
    layer_id: str | None = None
    active_stage_ids: tuple[str, ...] = ()
    face_ids: tuple[str, ...] = ()
    visible: bool = True
    locked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def volume(self) -> float:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return float(max(xmax - xmin, 0.0) * max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0))

    @property
    def centroid(self) -> tuple[float, float, float]:
        xmin, xmax, ymin, ymax, zmin, zmax = self.bounds
        return ((xmin + xmax) * 0.5, (ymin + ymax) * 0.5, (zmin + zmax) * 0.5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "bounds": [float(v) for v in self.bounds],
            "role": self.role,
            "material_id": self.material_id,
            "layer_id": self.layer_id,
            "active_stage_ids": list(self.active_stage_ids),
            "face_ids": list(self.face_ids),
            "visible": bool(self.visible),
            "locked": bool(self.locked),
            "volume": float(self.volume),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PartitionFeature:
    id: str
    type: Literal[
        "horizontal_layer",
        "vertical_plane",
        "polyline_extrusion",
        "excavation_surface",
        "borehole_layer",
        "imported_surface",
        "manual_split",
    ]
    parameters: dict[str, Any] = field(default_factory=dict)
    target_block_ids: tuple[str, ...] = ()
    generated_block_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "parameters": dict(self.parameters),
            "target_block_ids": list(self.target_block_ids),
            "generated_block_ids": list(self.generated_block_ids),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "BlockRole",
    "FaceBoundaryType",
    "SurfaceRole",
    "EdgeRole",
    "PointEntity",
    "EdgeEntity",
    "SurfaceEntity",
    "FaceEntity",
    "BlockEntity",
    "PartitionFeature",
]
