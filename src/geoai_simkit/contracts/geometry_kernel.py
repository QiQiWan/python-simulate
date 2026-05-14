from __future__ import annotations

"""Geometry-kernel contracts for production STL optimization and soil-layer partitioning.

The DTOs in this module are intentionally dependency-light.  They can describe
Gmsh/meshio-backed production paths when those optional dependencies are
available, while remaining usable in headless environments that rely on the
built-in deterministic fallbacks.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GeometryKernelDependencyStatus:
    gmsh_python_available: bool = False
    gmsh_executable_available: bool = False
    meshio_available: bool = False
    backend: str = "dependency_light"
    status: str = "fallback"
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    @property
    def gmsh_available(self) -> bool:
        return bool(self.gmsh_python_available or self.gmsh_executable_available)

    @property
    def production_tet4_available(self) -> bool:
        return bool(self.gmsh_available and self.meshio_available)

    def to_dict(self) -> dict[str, object]:
        return {
            "gmsh_python_available": bool(self.gmsh_python_available),
            "gmsh_executable_available": bool(self.gmsh_executable_available),
            "gmsh_available": self.gmsh_available,
            "meshio_available": bool(self.meshio_available),
            "production_tet4_available": self.production_tet4_available,
            "backend": self.backend,
            "status": self.status,
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "geometry_kernel_dependency_status_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class STLOptimizationAction:
    code: str
    message: str
    severity: str = "info"
    count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity.lower() in {"error", "blocking"}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "count": int(self.count),
            "blocking": self.blocking,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class STLOptimizationReport:
    ok: bool
    original_node_count: int = 0
    optimized_node_count: int = 0
    original_face_count: int = 0
    optimized_face_count: int = 0
    duplicate_node_count: int = 0
    degenerate_face_count: int = 0
    open_boundary_edge_count: int = 0
    nonmanifold_edge_count: int = 0
    closed: bool = False
    manifold: bool = False
    actions: tuple[STLOptimizationAction, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    @property
    def blocking_actions(self) -> tuple[STLOptimizationAction, ...]:
        return tuple(action for action in self.actions if action.blocking)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "original_node_count": int(self.original_node_count),
            "optimized_node_count": int(self.optimized_node_count),
            "original_face_count": int(self.original_face_count),
            "optimized_face_count": int(self.optimized_face_count),
            "duplicate_node_count": int(self.duplicate_node_count),
            "degenerate_face_count": int(self.degenerate_face_count),
            "open_boundary_edge_count": int(self.open_boundary_edge_count),
            "nonmanifold_edge_count": int(self.nonmanifold_edge_count),
            "closed": bool(self.closed),
            "manifold": bool(self.manifold),
            "blocking_actions": [row.to_dict() for row in self.blocking_actions],
            "actions": [row.to_dict() for row in self.actions],
            "metadata": {"contract": "stl_optimization_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class SoilLayerDefinition:
    layer_id: str
    z_min: float
    z_max: float
    material_id: str
    role: str = "soil"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "layer_id": self.layer_id,
            "z_min": float(self.z_min),
            "z_max": float(self.z_max),
            "material_id": self.material_id,
            "role": self.role,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SoilLayerCutReport:
    ok: bool
    layer_count: int = 0
    generated_cell_count: int = 0
    generated_node_count: int = 0
    material_ids: tuple[str, ...] = ()
    interface_candidate_count: int = 0
    element_family: str = "hex8"
    layers: tuple[SoilLayerDefinition, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "layer_count": int(self.layer_count),
            "generated_cell_count": int(self.generated_cell_count),
            "generated_node_count": int(self.generated_node_count),
            "material_ids": list(self.material_ids),
            "interface_candidate_count": int(self.interface_candidate_count),
            "element_family": self.element_family,
            "layers": [row.to_dict() for row in self.layers],
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "soil_layer_cut_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class GeometryKernelReport:
    ok: bool
    dependency_status: GeometryKernelDependencyStatus
    stl_optimization: STLOptimizationReport | None = None
    soil_layer_cut: SoilLayerCutReport | None = None
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "dependency_status": self.dependency_status.to_dict(),
            "stl_optimization": self.stl_optimization.to_dict() if self.stl_optimization is not None else None,
            "soil_layer_cut": self.soil_layer_cut.to_dict() if self.soil_layer_cut is not None else None,
            "metadata": {"contract": "geometry_kernel_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class GmshPhysicalGroupRecord:
    """Stable description of a Gmsh/meshio physical group or fallback equivalent."""

    name: str
    dimension: int
    tag: int = 0
    material_id: str = ""
    role: str = ""
    entity_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dimension": int(self.dimension),
            "tag": int(self.tag),
            "material_id": self.material_id,
            "role": self.role,
            "entity_count": int(self.entity_count),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GmshMeshioValidationReport:
    """Dependency and physical-group preservation report for production meshing."""

    ok: bool
    dependency_status: GeometryKernelDependencyStatus
    physical_groups: tuple[GmshPhysicalGroupRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "dependency_status": self.dependency_status.to_dict(),
            "physical_groups": [row.to_dict() for row in self.physical_groups],
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "gmsh_meshio_validation_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class SurfaceStratigraphyDefinition:
    """A layer bounded by two real imported stratigraphic surfaces."""

    layer_id: str
    top_surface_id: str
    bottom_surface_id: str
    material_id: str
    role: str = "soil"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "layer_id": self.layer_id,
            "top_surface_id": self.top_surface_id,
            "bottom_surface_id": self.bottom_surface_id,
            "material_id": self.material_id,
            "role": self.role,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StratigraphicClosureReport:
    """Report for sealing volumes between real stratigraphic surfaces."""

    ok: bool
    layer_count: int = 0
    generated_cell_count: int = 0
    generated_node_count: int = 0
    material_ids: tuple[str, ...] = ()
    surface_ids: tuple[str, ...] = ()
    interface_candidate_count: int = 0
    element_family: str = "hex8"
    layers: tuple[SurfaceStratigraphyDefinition, ...] = ()
    physical_groups: tuple[GmshPhysicalGroupRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "layer_count": int(self.layer_count),
            "generated_cell_count": int(self.generated_cell_count),
            "generated_node_count": int(self.generated_node_count),
            "material_ids": list(self.material_ids),
            "surface_ids": list(self.surface_ids),
            "interface_candidate_count": int(self.interface_candidate_count),
            "element_family": self.element_family,
            "layers": [row.to_dict() for row in self.layers],
            "physical_groups": [row.to_dict() for row in self.physical_groups],
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "stratigraphic_closure_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class MeshQualityOptimizationReport:
    """Report for local bad-cell filtering and quality-gate preparation."""

    ok: bool
    original_cell_count: int = 0
    optimized_cell_count: int = 0
    removed_bad_cell_count: int = 0
    min_volume_before: float | None = None
    min_volume_after: float | None = None
    max_aspect_ratio_before: float | None = None
    max_aspect_ratio_after: float | None = None
    bad_cell_ids: tuple[int, ...] = ()
    actions: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "original_cell_count": int(self.original_cell_count),
            "optimized_cell_count": int(self.optimized_cell_count),
            "removed_bad_cell_count": int(self.removed_bad_cell_count),
            "min_volume_before": self.min_volume_before,
            "min_volume_after": self.min_volume_after,
            "max_aspect_ratio_before": self.max_aspect_ratio_before,
            "max_aspect_ratio_after": self.max_aspect_ratio_after,
            "bad_cell_ids": [int(v) for v in self.bad_cell_ids],
            "actions": list(self.actions),
            "metadata": {"contract": "mesh_quality_optimization_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class LocalRemeshReport:
    """Report for local replacement of bad volume cells."""

    ok: bool
    original_cell_count: int = 0
    remeshed_bad_cell_count: int = 0
    removed_bad_cell_count: int = 0
    generated_replacement_cell_count: int = 0
    final_cell_count: int = 0
    bad_cell_ids: tuple[int, ...] = ()
    actions: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "original_cell_count": int(self.original_cell_count),
            "remeshed_bad_cell_count": int(self.remeshed_bad_cell_count),
            "removed_bad_cell_count": int(self.removed_bad_cell_count),
            "generated_replacement_cell_count": int(self.generated_replacement_cell_count),
            "final_cell_count": int(self.final_cell_count),
            "bad_cell_ids": [int(v) for v in self.bad_cell_ids],
            "actions": list(self.actions),
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "local_remesh_report_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class GmshOCCFragmentMeshingReport:
    """Report for production Gmsh/OCC fragment Tet4 meshing."""

    ok: bool
    dependency_status: GeometryKernelDependencyStatus
    backend: str = "gmsh_occ_fragment"
    occ_fragment_attempted: bool = False
    occ_fragment_used: bool = False
    meshio_conversion_used: bool = False
    generated_node_count: int = 0
    generated_cell_count: int = 0
    physical_groups: tuple[GmshPhysicalGroupRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()
    debug_files: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "dependency_status": self.dependency_status.to_dict(),
            "backend": self.backend,
            "occ_fragment_attempted": bool(self.occ_fragment_attempted),
            "occ_fragment_used": bool(self.occ_fragment_used),
            "meshio_conversion_used": bool(self.meshio_conversion_used),
            "generated_node_count": int(self.generated_node_count),
            "generated_cell_count": int(self.generated_cell_count),
            "physical_groups": [row.to_dict() for row in self.physical_groups],
            "diagnostics": list(self.diagnostics),
            "debug_files": list(self.debug_files),
            "metadata": {"contract": "gmsh_occ_fragment_meshing_report_v1", **dict(self.metadata)},
        }


__all__ = [
    "GeometryKernelDependencyStatus",
    "GmshOCCFragmentMeshingReport",
    "GeometryKernelReport",
    "GmshMeshioValidationReport",
    "GmshPhysicalGroupRecord",
    "LocalRemeshReport",
    "MeshQualityOptimizationReport",
    "STLOptimizationAction",
    "STLOptimizationReport",
    "SoilLayerCutReport",
    "SoilLayerDefinition",
    "StratigraphicClosureReport",
    "SurfaceStratigraphyDefinition",
]
