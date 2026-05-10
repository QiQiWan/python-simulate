from __future__ import annotations

"""Production meshing validation contracts.

These DTOs keep complex STL / volume-mesh validation dependency-light so GUI,
CLI, workflow and external plugin layers can exchange robust meshing diagnostics
without importing Gmsh, meshio, PyVista or solver internals.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class OptionalMesherDependencyStatus:
    """Availability report for optional production meshing dependencies."""

    gmsh_available: bool = False
    meshio_available: bool = False
    status: str = "missing_optional_dependency"
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    @property
    def production_tet4_available(self) -> bool:
        return bool(self.gmsh_available and self.meshio_available)

    def to_dict(self) -> dict[str, object]:
        return {
            "gmsh_available": bool(self.gmsh_available),
            "meshio_available": bool(self.meshio_available),
            "production_tet4_available": self.production_tet4_available,
            "status": self.status,
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "optional_mesher_dependency_status_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class STLRepairAction:
    """Recommended action for bringing an STL shell toward meshing readiness."""

    code: str
    message: str
    severity: str = "info"
    target: str = ""
    metadata: JsonMap = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity.lower() in {"error", "blocking"}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "target": self.target,
            "blocking": self.blocking,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class STLRepairReport:
    """Dependency-light STL shell repair/closure diagnosis."""

    ok: bool
    repairable: bool = True
    region_count: int = 0
    closed_region_count: int = 0
    open_boundary_edge_count: int = 0
    nonmanifold_edge_count: int = 0
    duplicate_node_count: int = 0
    degenerate_face_count: int = 0
    self_intersection_candidate_count: int = 0
    actions: tuple[STLRepairAction, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    @property
    def blocking_actions(self) -> tuple[STLRepairAction, ...]:
        return tuple(item for item in self.actions if item.blocking)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "repairable": bool(self.repairable),
            "region_count": int(self.region_count),
            "closed_region_count": int(self.closed_region_count),
            "open_boundary_edge_count": int(self.open_boundary_edge_count),
            "nonmanifold_edge_count": int(self.nonmanifold_edge_count),
            "duplicate_node_count": int(self.duplicate_node_count),
            "degenerate_face_count": int(self.degenerate_face_count),
            "self_intersection_candidate_count": int(self.self_intersection_candidate_count),
            "blocking_actions": [item.to_dict() for item in self.blocking_actions],
            "actions": [item.to_dict() for item in self.actions],
            "metadata": {"contract": "stl_repair_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class RegionMeshQualitySummary:
    """Per-region volume mesh quality summary."""

    region_id: str
    material_id: str = ""
    cell_count: int = 0
    min_volume: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.cell_count > 0 and self.bad_cell_count == 0)

    def to_dict(self) -> dict[str, object]:
        return {
            "region_id": self.region_id,
            "material_id": self.material_id,
            "cell_count": int(self.cell_count),
            "min_volume": self.min_volume,
            "max_aspect_ratio": self.max_aspect_ratio,
            "bad_cell_count": int(self.bad_cell_count),
            "ok": self.ok,
            "metadata": {"contract": "region_mesh_quality_summary_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class InterfaceConformityReport:
    """Conformity summary for multi-region volume mesh interfaces."""

    ok: bool
    candidate_count: int = 0
    conformal_pair_count: int = 0
    nonconformal_pair_count: int = 0
    missing_interface_material_count: int = 0
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "candidate_count": int(self.candidate_count),
            "conformal_pair_count": int(self.conformal_pair_count),
            "nonconformal_pair_count": int(self.nonconformal_pair_count),
            "missing_interface_material_count": int(self.missing_interface_material_count),
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "interface_conformity_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class ProductionMeshingValidationReport:
    """Aggregated production meshing validation report."""

    ok: bool
    dependency_status: OptionalMesherDependencyStatus
    stl_repair: STLRepairReport
    mesh_quality: JsonMap = field(default_factory=dict)
    material_compatibility: JsonMap = field(default_factory=dict)
    interface_conformity: InterfaceConformityReport = field(default_factory=lambda: InterfaceConformityReport(ok=True))
    region_quality: tuple[RegionMeshQualitySummary, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "dependency_status": self.dependency_status.to_dict(),
            "stl_repair": self.stl_repair.to_dict(),
            "mesh_quality": dict(self.mesh_quality),
            "material_compatibility": dict(self.material_compatibility),
            "interface_conformity": self.interface_conformity.to_dict(),
            "region_quality": [item.to_dict() for item in self.region_quality],
            "metadata": {"contract": "production_meshing_validation_report_v1", **dict(self.metadata)},
        }


__all__ = [
    "InterfaceConformityReport",
    "OptionalMesherDependencyStatus",
    "ProductionMeshingValidationReport",
    "RegionMeshQualitySummary",
    "STLRepairAction",
    "STLRepairReport",
]
