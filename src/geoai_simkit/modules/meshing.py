from __future__ import annotations

"""Stable facade for project meshing workflows."""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import MeshGenerator, MeshGeneratorRegistry, MeshRequest, MeshResult, ProjectMutation, SolidAnalysisReadinessReport, project_mesh_summary
from geoai_simkit.mesh.generator_registry import get_default_mesh_generator_registry, mesh_generator_descriptors, register_mesh_generator as _register_mesh_generator
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness as _validate_solid_analysis_readiness
from geoai_simkit.mesh.multi_region_stl import audit_region_material_mapping as _audit_region_material_mapping, diagnose_multi_stl_closure as _diagnose_multi_stl_closure
from geoai_simkit.solver.contact_readiness import validate_interface_contact_readiness as _validate_interface_contact_readiness
from geoai_simkit.services.quality_gates import evaluate_mesh_quality_gate as _evaluate_mesh_quality_gate
from geoai_simkit.services.production_meshing_validation import analyze_stl_repair_readiness as _analyze_stl_repair_readiness, build_production_meshing_validation_report as _build_production_meshing_validation_report, build_region_mesh_quality_summary as _build_region_mesh_quality_summary, optional_mesher_dependency_status as _optional_mesher_dependency_status, validate_interface_conformity as _validate_interface_conformity
from geoai_simkit.services.complete_3d_mesh import build_complete_3d_mesh_report as _build_complete_3d_mesh_report, project_3d_boundary_faces as _project_3d_boundary_faces, supported_3d_mesh_generators as _supported_3d_mesh_generators, tag_project_3d_boundary_faces as _tag_project_3d_boundary_faces
from geoai_simkit.services.geometry_kernel import build_geometry_kernel_report as _build_geometry_kernel_report, build_soil_layer_volume_mesh as _build_soil_layer_volume_mesh, build_stratigraphic_surface_volume_mesh as _build_stratigraphic_surface_volume_mesh, build_gmsh_occ_fragment_tet4_mesh as _build_gmsh_occ_fragment_tet4_mesh, geometry_kernel_dependency_status as _geometry_kernel_dependency_status, geometry_operation_log_status as _geometry_operation_log_status, gmsh_meshio_validation_report as _gmsh_meshio_validation_report, local_remesh_volume_mesh_quality as _local_remesh_volume_mesh_quality, optimize_complex_stl_surface_mesh as _optimize_complex_stl_surface_mesh, optimize_stl_surface_mesh as _optimize_stl_surface_mesh, optimize_volume_mesh_quality as _optimize_volume_mesh_quality
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module

MODULE_KEY = "meshing"
def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def mesh_generator_registry() -> MeshGeneratorRegistry:
    return get_default_mesh_generator_registry()


def register_mesh_generator(generator: MeshGenerator, *, replace: bool = False) -> None:
    _register_mesh_generator(generator, replace=replace)


def supported_mesh_generators() -> list[str]:
    return mesh_generator_registry().keys()


def generate_project_mesh(
    project: Any,
    *,
    mesh_kind: str = "auto",
    attach: bool = True,
    options: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MeshResult:
    context = as_project_context(project)
    request = MeshRequest(
        project=context,
        mesh_kind=mesh_kind,
        options=dict(options or {}),
        attach=bool(attach),
        metadata=dict(metadata or {}),
    )
    generator = mesh_generator_registry().resolve(request)
    result = generator.generate(request)
    if result.attached:
        apply_mutation = getattr(context, "apply_mutation", None)
        if callable(apply_mutation):
            apply_mutation(
                ProjectMutation(
                    action=f"generate_mesh:{result.mesh_kind}",
                    channels=("mesh",),
                    affected_entities=tuple(str(item) for item in getattr(result.mesh, "block_ids", lambda: [])()),
                )
            )
    return result


def current_project_mesh(project: Any) -> Any:
    return as_project_context(project).current_mesh()


def current_project_mesh_summary(project: Any) -> dict[str, Any]:
    return project_mesh_summary(as_project_context(project)).to_dict()


def validate_solid_analysis_readiness(project: Any) -> SolidAnalysisReadinessReport:
    """Return a structured readiness report for 3D solid FEM analysis."""

    return _validate_solid_analysis_readiness(as_project_context(project))


def diagnose_multi_stl_closure(project: Any) -> dict[str, Any]:
    """Diagnose whether imported STL regions form closed shells for conformal Tet4 meshing."""

    mesh = as_project_context(project).current_mesh()
    if mesh is None:
        return {"ready": False, "region_count": 0, "issues": [{"severity": "error", "code": "mesh.missing"}]}
    return _diagnose_multi_stl_closure(mesh).to_dict()


def audit_region_material_mapping(project: Any) -> dict[str, Any]:
    """Audit material_id tags on mesh regions against the project material library."""

    context = as_project_context(project)
    target = context.get_project() if hasattr(context, "get_project") else project
    return _audit_region_material_mapping(target)



def evaluate_project_mesh_quality(project: Any, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 100.0) -> dict[str, Any]:
    """Evaluate solid-cell quality before a verified 3D solve."""

    return _evaluate_mesh_quality_gate(as_project_context(project), min_volume=min_volume, max_aspect_ratio=max_aspect_ratio).to_dict()



def geometry_kernel_dependency_status() -> dict[str, Any]:
    """Return optional Gmsh/meshio and dependency-light geometry-kernel status."""

    return _geometry_kernel_dependency_status().to_dict()


def optimize_project_stl_surface(project: Any, *, tolerance: float = 1.0e-9, attach: bool = True) -> dict[str, Any]:
    """Optimize the current STL surface mesh by merging duplicate nodes and removing degenerate faces."""

    mesh, report = _optimize_stl_surface_mesh(as_project_context(project), tolerance=tolerance, attach=attach)
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def optimize_project_complex_stl_surface(
    project: Any,
    *,
    tolerance: float = 1.0e-9,
    fill_holes: bool = True,
    max_hole_edges: int = 64,
    orient_normals: bool = True,
    detect_self_intersections: bool = True,
    attach: bool = True,
) -> dict[str, Any]:
    """Run production STL pre-flight repair: hole patching, normal orientation and self-intersection diagnostics."""

    mesh, report = _optimize_complex_stl_surface_mesh(
        as_project_context(project),
        tolerance=tolerance,
        fill_holes=fill_holes,
        max_hole_edges=max_hole_edges,
        orient_normals=orient_normals,
        detect_self_intersections=detect_self_intersections,
        attach=attach,
    )
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def gmsh_meshio_validation(project: Any) -> dict[str, Any]:
    """Return Gmsh/meshio health and physical-group preservation diagnostics."""

    return _gmsh_meshio_validation_report(as_project_context(project)).to_dict()




def gmsh_occ_fragment_tet4_mesh(
    project: Any,
    *,
    layers: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    mesh_size: float | None = None,
    attach: bool = True,
    allow_fallback: bool = True,
    debug: bool | None = None,
    debug_dir: str | None = None,
) -> dict[str, Any]:
    """Run production Gmsh/OCC fragment Tet4 meshing, with explicit fallback diagnostics."""

    mesh, report = _build_gmsh_occ_fragment_tet4_mesh(
        as_project_context(project),
        layers=layers,
        mesh_size=mesh_size,
        attach=attach,
        allow_fallback=allow_fallback,
        debug=debug,
        debug_dir=debug_dir,
    )
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def local_remesh_project_volume_mesh_quality(
    project: Any,
    *,
    min_volume: float = 1.0e-12,
    max_aspect_ratio: float = 1.0e6,
    attach: bool = True,
    debug: bool | None = None,
    debug_dir: str | None = None,
) -> dict[str, Any]:
    """Locally remesh bad Tet4/Hex8 cells instead of only filtering them out."""

    mesh, report = _local_remesh_volume_mesh_quality(
        as_project_context(project),
        min_volume=min_volume,
        max_aspect_ratio=max_aspect_ratio,
        attach=attach,
        debug=debug,
        debug_dir=debug_dir,
    )
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def geometry_operation_log_status() -> dict[str, Any]:
    """Return geometry-kernel logging/debug status."""

    return dict(_geometry_operation_log_status())


def generate_stratigraphic_surface_volume_mesh(
    project: Any,
    *,
    layers: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    dims: tuple[int, int] = (1, 1),
    element_family: str = "hex8",
    attach: bool = True,
) -> dict[str, Any]:
    """Generate a 3D volume mesh by sealing real top/bottom stratigraphic STL surfaces."""

    mesh, report = _build_stratigraphic_surface_volume_mesh(as_project_context(project), layers=layers, dims=dims, element_family=element_family, attach=attach)
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def optimize_project_volume_mesh_quality(project: Any, *, min_volume: float = 1.0e-12, max_aspect_ratio: float = 1.0e6, attach: bool = True) -> dict[str, Any]:
    """Remove locally invalid or extremely poor-quality volume cells before solve."""

    mesh, report = _optimize_volume_mesh_quality(as_project_context(project), min_volume=min_volume, max_aspect_ratio=max_aspect_ratio, attach=attach)
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def generate_soil_layer_volume_mesh(
    project: Any,
    *,
    layers: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    dims: tuple[int, int] = (1, 1),
    element_family: str = "hex8",
    attach: bool = True,
) -> dict[str, Any]:
    """Generate a 3D soil-layer volume mesh from the current STL surface bounds."""

    mesh, report = _build_soil_layer_volume_mesh(as_project_context(project), layers=layers, dims=dims, element_family=element_family, attach=attach)
    payload = report.to_dict()
    payload["attached"] = bool(attach and mesh is not None)
    return payload


def geometry_kernel_report(project: Any) -> dict[str, Any]:
    """Return the strengthened geometry-kernel status and STL optimization diagnostics."""

    return _build_geometry_kernel_report(as_project_context(project)).to_dict()

def optional_mesher_dependency_status() -> dict[str, Any]:
    """Return Gmsh/meshio dependency health for production meshing."""

    return _optional_mesher_dependency_status().to_dict()


def analyze_stl_repair_readiness(project: Any) -> dict[str, Any]:
    """Return STL repair/closure diagnostics before production Tet4 meshing."""

    return _analyze_stl_repair_readiness(as_project_context(project)).to_dict()


def production_meshing_validation(project: Any, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    """Return aggregated production meshing validation diagnostics."""

    return _build_production_meshing_validation_report(as_project_context(project), solver_backend=solver_backend).to_dict()


def region_mesh_quality_summary(project: Any) -> list[dict[str, Any]]:
    """Return per-region mesh quality summaries for solid volume meshes."""

    return [item.to_dict() for item in _build_region_mesh_quality_summary(as_project_context(project))]


def interface_conformity_report(project: Any) -> dict[str, Any]:
    """Return multi-region interface conformity diagnostics."""

    return _validate_interface_conformity(as_project_context(project)).to_dict()


def supported_3d_mesh_generators() -> list[str]:
    """Return registered mesh generators capable of producing 3D solid volume meshes."""

    return list(_supported_3d_mesh_generators())


def tag_project_3d_boundary_faces(project: Any) -> dict[str, Any]:
    """Extract and attach complete 3D boundary face tags to the current mesh."""

    return _tag_project_3d_boundary_faces(as_project_context(project)).to_dict()


def project_3d_boundary_faces(project: Any) -> list[dict[str, Any]]:
    """Return complete exterior boundary faces for the current 3D solid mesh."""

    return _project_3d_boundary_faces(as_project_context(project))


def complete_3d_mesh_report(project: Any, *, solver_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    """Return the complete 3D mesh capability report for a project."""

    return _build_complete_3d_mesh_report(as_project_context(project), solver_backend=solver_backend).to_dict()

def validate_interface_contact_readiness(project: Any) -> dict[str, Any]:
    """Return contact/interface readiness for materialized STL region interfaces."""

    context = as_project_context(project)
    target = context.get_project() if hasattr(context, "get_project") else project
    return _validate_interface_contact_readiness(target)


def smoke_check() -> dict[str, Any]:
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "registry_available": bool(supported_mesh_generators()),
            "layered_adapter_available": "layered" in supported_mesh_generators(),
            "preview_adapter_available": "tagged_preview" in supported_mesh_generators(),
            "voxel_stl_adapter_available": "voxel_hex8_from_stl" in supported_mesh_generators(),
            "gmsh_stl_adapter_available": "gmsh_tet4_from_stl" in supported_mesh_generators(),
            "conformal_multi_stl_adapter_available": "conformal_tet4_from_stl_regions" in supported_mesh_generators(),
            "structured_hex8_box_available": "structured_hex8_box" in supported_mesh_generators(),
            "structured_tet4_box_available": "structured_tet4_box" in supported_mesh_generators(),
            "complete_3d_mesh_report_entrypoint": callable(complete_3d_mesh_report),
            "soil_layered_volume_from_stl_available": "soil_layered_volume_from_stl" in supported_mesh_generators(),
            "geometry_kernel_entrypoint": callable(geometry_kernel_report),
            "complex_stl_optimizer_entrypoint": callable(optimize_project_complex_stl_surface),
            "stratigraphic_surface_volume_from_stl_available": "stratigraphic_surface_volume_from_stl" in supported_mesh_generators(),
            "gmsh_occ_fragment_tet4_from_stl_available": "gmsh_occ_fragment_tet4_from_stl" in supported_mesh_generators(),
            "production_meshing_validation_entrypoint": callable(production_meshing_validation),
        },
    )


__all__ = [
    "MeshRequest",
    "MeshResult",
    "current_project_mesh",
    "current_project_mesh_summary",
    "describe_module",
    "audit_region_material_mapping",
    "diagnose_multi_stl_closure",
    "generate_project_mesh",
    "geometry_kernel_dependency_status",
    "optimize_project_stl_surface",
    "optimize_project_complex_stl_surface",
    "gmsh_meshio_validation",
    "generate_stratigraphic_surface_volume_mesh",
    "optimize_project_volume_mesh_quality",
    "generate_soil_layer_volume_mesh",
    "geometry_kernel_report",
    "gmsh_occ_fragment_tet4_mesh",
    "local_remesh_project_volume_mesh_quality",
    "geometry_operation_log_status",
    "optional_mesher_dependency_status",
    "analyze_stl_repair_readiness",
    "production_meshing_validation",
    "region_mesh_quality_summary",
    "interface_conformity_report",
    "evaluate_project_mesh_quality",
    "supported_3d_mesh_generators",
    "tag_project_3d_boundary_faces",
    "project_3d_boundary_faces",
    "complete_3d_mesh_report",
    "validate_interface_contact_readiness",
    "mesh_generator_registry",
    "mesh_generator_descriptors",
    "register_mesh_generator",
    "smoke_check",
    "supported_mesh_generators",
    "validate_solid_analysis_readiness",
]
