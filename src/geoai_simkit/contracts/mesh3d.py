from __future__ import annotations

"""Complete 3D mesh contracts.

These contracts describe solver-ready 3D mesh topology without exposing concrete
mesh implementation objects.  They are intentionally dependency-light so module
facades, workflow reports, GUI controllers and external plugins can exchange the
same 3D mesh diagnostics.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Mesh3DBoundaryFace:
    """One exterior face of a 3D solid cell."""

    face_id: int
    cell_id: int
    cell_type: str
    nodes: tuple[int, ...]
    boundary_set: str = "external"
    region_id: str = ""
    material_id: str = ""
    centroid: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "face_id": int(self.face_id),
            "cell_id": int(self.cell_id),
            "cell_type": self.cell_type,
            "nodes": list(self.nodes),
            "boundary_set": self.boundary_set,
            "region_id": self.region_id,
            "material_id": self.material_id,
            "centroid": list(self.centroid),
            "normal": list(self.normal),
            "metadata": {"contract": "mesh3d_boundary_face_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class Mesh3DBoundarySet:
    """Named group of exterior faces for boundary conditions and loads."""

    name: str
    face_count: int = 0
    cell_count: int = 0
    node_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "face_count": int(self.face_count),
            "cell_count": int(self.cell_count),
            "node_count": int(self.node_count),
            "metadata": {"contract": "mesh3d_boundary_set_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class Mesh3DRegion:
    """One solid volume region with material mapping."""

    region_id: str
    material_id: str = ""
    cell_count: int = 0
    node_count: int = 0
    cell_types: tuple[str, ...] = ()
    volume: float | None = None
    metadata: JsonMap = field(default_factory=dict)

    @property
    def material_mapped(self) -> bool:
        return bool(self.material_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "region_id": self.region_id,
            "material_id": self.material_id,
            "material_mapped": self.material_mapped,
            "cell_count": int(self.cell_count),
            "node_count": int(self.node_count),
            "cell_types": list(self.cell_types),
            "volume": self.volume,
            "metadata": {"contract": "mesh3d_region_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class Mesh3DInterfacePair:
    """Internal interface candidate between two material/region groups."""

    pair_id: str
    region_a: str
    region_b: str
    face_count: int = 0
    conformal: bool = True
    materialized: bool = False
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "pair_id": self.pair_id,
            "region_a": self.region_a,
            "region_b": self.region_b,
            "face_count": int(self.face_count),
            "conformal": bool(self.conformal),
            "materialized": bool(self.materialized),
            "metadata": {"contract": "mesh3d_interface_pair_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class Mesh3DTopologyReport:
    """Topology summary of a solid 3D mesh."""

    ok: bool
    node_count: int = 0
    cell_count: int = 0
    solid_cell_count: int = 0
    surface_cell_count: int = 0
    boundary_face_count: int = 0
    internal_face_count: int = 0
    nonmanifold_face_count: int = 0
    regions: tuple[Mesh3DRegion, ...] = ()
    boundary_sets: tuple[Mesh3DBoundarySet, ...] = ()
    interface_pairs: tuple[Mesh3DInterfacePair, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "solid_cell_count": int(self.solid_cell_count),
            "surface_cell_count": int(self.surface_cell_count),
            "boundary_face_count": int(self.boundary_face_count),
            "internal_face_count": int(self.internal_face_count),
            "nonmanifold_face_count": int(self.nonmanifold_face_count),
            "regions": [item.to_dict() for item in self.regions],
            "boundary_sets": [item.to_dict() for item in self.boundary_sets],
            "interface_pairs": [item.to_dict() for item in self.interface_pairs],
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "mesh3d_topology_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class Complete3DMeshReport:
    """Aggregated report proving a project has complete 3D mesh capability."""

    ok: bool
    topology: Mesh3DTopologyReport
    solid_readiness: JsonMap = field(default_factory=dict)
    production_validation: JsonMap = field(default_factory=dict)
    supported_generators: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "topology": self.topology.to_dict(),
            "solid_readiness": dict(self.solid_readiness),
            "production_validation": dict(self.production_validation),
            "supported_generators": list(self.supported_generators),
            "capabilities": list(self.capabilities),
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "complete_3d_mesh_report_v1", **dict(self.metadata)},
        }


__all__ = [
    "Complete3DMeshReport",
    "Mesh3DBoundaryFace",
    "Mesh3DBoundarySet",
    "Mesh3DInterfacePair",
    "Mesh3DRegion",
    "Mesh3DTopologyReport",
]
