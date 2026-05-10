from __future__ import annotations

"""Geometry kernel abstraction for visual modeling tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.geometry.entities import BlockEntity, EdgeEntity, FaceEntity, PartitionFeature, PointEntity, SurfaceEntity
from geoai_simkit.geometry.topology_graph import TopologyGraph


@dataclass(slots=True)
class GeometryDocument:
    points: dict[str, PointEntity] = field(default_factory=dict)
    edges: dict[str, EdgeEntity] = field(default_factory=dict)
    surfaces: dict[str, SurfaceEntity] = field(default_factory=dict)
    blocks: dict[str, BlockEntity] = field(default_factory=dict)
    faces: dict[str, FaceEntity] = field(default_factory=dict)
    partition_features: dict[str, PartitionFeature] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def point_rows(self) -> list[dict[str, Any]]:
        return [point.to_dict() for point in self.points.values()]

    def edge_rows(self) -> list[dict[str, Any]]:
        return [edge.to_dict() for edge in self.edges.values()]

    def surface_rows(self) -> list[dict[str, Any]]:
        return [surface.to_dict() for surface in self.surfaces.values()]

    def block_rows(self) -> list[dict[str, Any]]:
        return [block.to_dict() for block in self.blocks.values()]

    def face_rows(self) -> list[dict[str, Any]]:
        return [face.to_dict() for face in self.faces.values()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": self.point_rows(),
            "edges": self.edge_rows(),
            "surfaces": self.surface_rows(),
            "blocks": self.block_rows(),
            "faces": self.face_rows(),
            "partition_features": [item.to_dict() for item in self.partition_features.values()],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GeometryBuildResult:
    geometry: GeometryDocument
    topology: TopologyGraph
    artifact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"geometry": self.geometry.to_dict(), "topology": self.topology.to_dict(), "artifact": dict(self.artifact)}


class GeometryKernel(ABC):
    name: str = "geometry_kernel"

    @abstractmethod
    def create_foundation_pit(self, parameters: dict[str, Any] | None = None) -> GeometryBuildResult:
        """Create a foundation-pit engineering geometry document."""

    @abstractmethod
    def split_by_horizontal_layers(self, document: GeometryDocument, levels: list[float]) -> GeometryDocument:
        """Split soil blocks by horizontal levels."""

    @abstractmethod
    def split_by_excavation(self, document: GeometryDocument, excavation_levels: list[float]) -> GeometryDocument:
        """Split excavation blocks by excavation levels."""

    @abstractmethod
    def find_adjacent_faces(self, document: GeometryDocument) -> TopologyGraph:
        """Rebuild or update adjacency/contact topology."""
