from __future__ import annotations

"""Complete 3D mesh service boundary.

This service aggregates topology extraction, boundary face tagging, solid
readiness and production meshing validation without importing GUI or solver
runtime internals.
"""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts.mesh3d import Complete3DMeshReport, Mesh3DTopologyReport
from geoai_simkit.mesh.complete_3d import apply_3d_boundary_tags, build_mesh3d_topology_report, extract_3d_boundary_faces
from geoai_simkit.mesh.generator_registry import mesh_generator_descriptors
from geoai_simkit.mesh.solid_readiness import validate_solid_analysis_readiness
from geoai_simkit.services.production_meshing_validation import build_production_meshing_validation_report


def _mesh(project_or_port: Any) -> Any:
    return as_project_context(project_or_port).current_mesh()


def supported_3d_mesh_generators() -> tuple[str, ...]:
    rows = mesh_generator_descriptors()
    keys: list[str] = []
    for row in rows:
        key = str(row.get("key") or "")
        caps = row.get("capabilities") or {}
        features = tuple(str(item) for item in (caps.get("features") if isinstance(caps, dict) else ()) or ())
        outputs = tuple(str(item) for item in (caps.get("supported_outputs") if isinstance(caps, dict) else ()) or ())
        if any(token in features for token in ("3d_volume", "stl_surface_to_volume", "conformal_tet4", "hex8", "tet4")) or any("solid_volume" in item for item in outputs):
            keys.append(key)
    return tuple(sorted(key for key in keys if key))


def tag_project_3d_boundary_faces(project_or_port: Any) -> Mesh3DTopologyReport:
    mesh = _mesh(project_or_port)
    if mesh is None:
        return Mesh3DTopologyReport(ok=False, diagnostics=("mesh3d.mesh_missing",))
    return apply_3d_boundary_tags(mesh)


def project_3d_boundary_faces(project_or_port: Any) -> list[dict[str, object]]:
    mesh = _mesh(project_or_port)
    if mesh is None:
        return []
    return [face.to_dict() for face in extract_3d_boundary_faces(mesh)]


def build_complete_3d_mesh_report(project_or_port: Any, *, solver_backend: str = "solid_linear_static_cpu") -> Complete3DMeshReport:
    context = as_project_context(project_or_port)
    mesh = context.current_mesh()
    if mesh is None:
        topology = Mesh3DTopologyReport(ok=False, diagnostics=("mesh3d.mesh_missing",))
        return Complete3DMeshReport(
            ok=False,
            topology=topology,
            supported_generators=supported_3d_mesh_generators(),
            diagnostics=("mesh3d.mesh_missing",),
            metadata={"contract_version": "complete_3d_mesh_report_v1"},
        )
    topology = apply_3d_boundary_tags(mesh)
    readiness = validate_solid_analysis_readiness(context).to_dict()
    production = build_production_meshing_validation_report(context, solver_backend=solver_backend).to_dict()
    diagnostics = list(topology.diagnostics)
    if not bool(readiness.get("ready")):
        diagnostics.append("mesh3d.solid_readiness_not_ready")
    if not bool(production.get("ok")):
        diagnostics.append("mesh3d.production_validation_not_ok")
    # Complete 3D mesh capability is a mesh/topology readiness claim.
    # Solver-specific material compatibility remains visible in production_validation
    # but does not make boundary-face extraction or 3D volume meshing incomplete.
    ok = bool(topology.ok and readiness.get("ready"))
    return Complete3DMeshReport(
        ok=ok,
        topology=topology,
        solid_readiness=readiness,
        production_validation=production,
        supported_generators=supported_3d_mesh_generators(),
        capabilities=(
            "tet4_volume_mesh",
            "hex8_volume_mesh",
            "boundary_face_sets",
            "region_material_tags",
            "interface_candidates",
            "quality_gate",
            "workflow_artifact",
        ),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        metadata={"contract_version": "complete_3d_mesh_report_v1", "solver_backend": solver_backend},
    )


__all__ = [
    "build_complete_3d_mesh_report",
    "project_3d_boundary_faces",
    "supported_3d_mesh_generators",
    "tag_project_3d_boundary_faces",
]
