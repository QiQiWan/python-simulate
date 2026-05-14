from __future__ import annotations

"""Build CAD-derived FEM preprocessor metadata from canonical topology identity.

The service converts face/edge/solid topology identities into the information a
finite-element workflow needs before meshing and solving: physical groups,
boundary/load candidates, mesh controls and explicit readiness blockers.  It is
headless and does not invoke Gmsh, OCC, Qt or PyVista.
"""

from typing import Any

from geoai_simkit.core.cad_fem_preprocessor import (
    CAD_FEM_PREPROCESSOR_CONTRACT,
    CadFemBoundaryCandidate,
    CadFemMeshControl,
    CadFemPhysicalGroup,
    CadFemReadinessReport,
)
from geoai_simkit.core.topology_identity import TopologyElementIdentity
from geoai_simkit.services.topology_identity_service import build_topology_identity_index, validate_topology_identity_index


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value)).strip("_") or "item"


def _merge_bounds(rows: list[tuple[float, float, float, float, float, float]]) -> tuple[float, float, float, float, float, float] | None:
    if not rows:
        return None
    return (
        min(row[0] for row in rows),
        max(row[1] for row in rows),
        min(row[2] for row in rows),
        max(row[3] for row in rows),
        min(row[4] for row in rows),
        max(row[5] for row in rows),
    )


def _project_bounds(project: Any, topology_rows: list[TopologyElementIdentity]) -> tuple[float, float, float, float, float, float] | None:
    rows: list[tuple[float, float, float, float, float, float]] = []
    geom = getattr(project, "geometry_model", None)
    for volume in list(getattr(geom, "volumes", {}) .values()) if geom is not None else []:
        bounds = getattr(volume, "bounds", None)
        if bounds is not None:
            rows.append(tuple(float(v) for v in list(bounds)[:6]))
    for item in topology_rows:
        if item.bounds is not None and item.kind == "solid":
            rows.append(tuple(float(v) for v in item.bounds))
    return _merge_bounds(rows)


def _extent(bounds: tuple[float, float, float, float, float, float]) -> tuple[float, float, float]:
    return (abs(bounds[1] - bounds[0]), abs(bounds[3] - bounds[2]), abs(bounds[5] - bounds[4]))


def _flat_axis(bounds: tuple[float, float, float, float, float, float], *, tol: float = 1.0e-8) -> str:
    dx, dy, dz = _extent(bounds)
    span = max(dx, dy, dz, 1.0)
    if dx <= tol * span:
        return "x"
    if dy <= tol * span:
        return "y"
    if dz <= tol * span:
        return "z"
    return ""


def _face_role(bounds: tuple[float, float, float, float, float, float] | None, project_bounds: tuple[float, float, float, float, float, float] | None, orientation: str = "") -> tuple[str, str]:
    if bounds is None:
        return "face_boundary_candidate", ""
    axis = _flat_axis(bounds)
    orient = str(orientation or "").lower()
    if project_bounds is None:
        if "bottom" in orient or "base" in orient:
            return "fixed_base", axis
        if "top" in orient or "free" in orient:
            return "load_or_free_surface", axis
        if "side" in orient or "xmin" in orient or "xmax" in orient or "ymin" in orient or "ymax" in orient:
            return "roller_side", axis
        return "face_boundary_candidate", axis
    tol = max(project_bounds[1] - project_bounds[0], project_bounds[3] - project_bounds[2], project_bounds[5] - project_bounds[4], 1.0) * 1.0e-7
    if axis == "z" and abs(bounds[4] - project_bounds[4]) <= tol and abs(bounds[5] - project_bounds[4]) <= tol:
        return "fixed_base", axis
    if axis == "z" and abs(bounds[4] - project_bounds[5]) <= tol and abs(bounds[5] - project_bounds[5]) <= tol:
        return "load_or_free_surface", axis
    if axis == "x" and (abs(bounds[0] - project_bounds[0]) <= tol or abs(bounds[1] - project_bounds[1]) <= tol):
        return "roller_side", axis
    if axis == "y" and (abs(bounds[2] - project_bounds[2]) <= tol or abs(bounds[3] - project_bounds[3]) <= tol):
        return "roller_side", axis
    return "internal_partition_or_interface", axis


def _material_ids(project: Any) -> set[str]:
    library = getattr(project, "material_library", None)
    if library is not None and hasattr(library, "material_ids"):
        try:
            return set(str(v) for v in library.material_ids())
        except Exception:
            return set()
    return set()


def _mesh_size(project: Any, default_element_size: float | None) -> float | None:
    if default_element_size is not None:
        return float(default_element_size)
    try:
        return float(project.mesh_model.mesh_settings.global_size)
    except Exception:
        return None


def _physical_group_id(kind: str, identity: TopologyElementIdentity) -> str:
    source = identity.source_entity_id or identity.shape_id or identity.id
    return f"pg_{kind}_{_safe_id(source)}"


def _physical_groups(topology_rows: list[TopologyElementIdentity]) -> list[CadFemPhysicalGroup]:
    groups: dict[str, CadFemPhysicalGroup] = {}
    for item in topology_rows:
        if item.kind == "solid":
            gid = _physical_group_id("volume", item)
            groups.setdefault(
                gid,
                CadFemPhysicalGroup(
                    id=gid,
                    name=gid,
                    dimension=3,
                    topology_keys=[],
                    source_entity_ids=[],
                    material_id=item.material_id,
                    phase_ids=list(item.phase_ids),
                    role=item.role or "volume_region",
                    metadata={"kind": "solid"},
                ),
            )
            g = groups[gid]
            if item.key not in g.topology_keys:
                g.topology_keys.append(item.key)
            if item.source_entity_id and item.source_entity_id not in g.source_entity_ids:
                g.source_entity_ids.append(item.source_entity_id)
        elif item.kind == "face":
            gid = _physical_group_id("surface", item)
            groups.setdefault(
                gid,
                CadFemPhysicalGroup(
                    id=gid,
                    name=gid,
                    dimension=2,
                    topology_keys=[],
                    source_entity_ids=[],
                    material_id=item.material_id,
                    phase_ids=list(item.phase_ids),
                    role="surface_boundary",
                    metadata={"kind": "face"},
                ),
            )
            g = groups[gid]
            if item.key not in g.topology_keys:
                g.topology_keys.append(item.key)
            if item.source_entity_id and item.source_entity_id not in g.source_entity_ids:
                g.source_entity_ids.append(item.source_entity_id)
    return list(groups.values())


def _boundary_candidates(topology_rows: list[TopologyElementIdentity], project_bounds: tuple[float, float, float, float, float, float] | None) -> list[CadFemBoundaryCandidate]:
    out: list[CadFemBoundaryCandidate] = []
    for item in topology_rows:
        if item.kind not in {"face", "edge"}:
            continue
        if item.kind == "face":
            role, normal_axis = _face_role(item.bounds, project_bounds, str(item.metadata.get("orientation") or item.native_tag or item.persistent_name))
            dim = 2
            pg = _physical_group_id("surface", item)
        else:
            role, normal_axis = "line_load_or_snap_reference", ""
            dim = 1
            pg = f"pg_curve_{_safe_id(item.source_entity_id or item.id)}"
        out.append(
            CadFemBoundaryCandidate(
                id=f"candidate:{item.kind}:{item.id}",
                topology_key=item.key,
                topology_id=item.id,
                shape_id=item.shape_id,
                topology_kind=str(item.kind),
                source_entity_id=item.source_entity_id,
                candidate_role=role,
                dimension=dim,
                normal_axis=normal_axis,
                bounds=item.bounds,
                material_id=item.material_id,
                phase_ids=list(item.phase_ids),
                physical_group_id=pg,
                confidence=item.confidence,
                metadata={"persistent_name": item.persistent_name, "native_tag": item.native_tag, **dict(item.metadata)},
            )
        )
    return out


def _mesh_controls(topology_rows: list[TopologyElementIdentity], *, element_size: float | None) -> list[CadFemMeshControl]:
    controls: list[CadFemMeshControl] = []
    for item in topology_rows:
        if item.kind == "solid":
            controls.append(
                CadFemMeshControl(
                    id=f"mesh_control:solid:{item.id}",
                    target_key=item.key,
                    target_kind="solid",
                    element_size=element_size,
                    growth_rate=1.35,
                    priority=10,
                    method="tet4",
                    reason="volume_physical_group",
                    metadata={"source_entity_id": item.source_entity_id},
                )
            )
    return controls


def _solver_requirements(project: Any, *, mesh_controls: list[CadFemMeshControl]) -> dict[str, Any]:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    settings = getattr(getattr(project, "mesh_model", None), "mesh_settings", None)
    return {
        "mesh_required_before_solve": True,
        "has_attached_mesh": mesh is not None,
        "mesh_cell_count": int(getattr(mesh, "cell_count", 0) or 0) if mesh is not None else 0,
        "required_cell_family": str(getattr(settings, "element_family", "tet4") or "tet4"),
        "local_mesh_control_count": len(mesh_controls),
        "requires_material_per_active_volume": True,
        "requires_displacement_constraints": True,
        "requires_phase_activation_plan": True,
        "requires_physical_groups": True,
    }


def build_cad_fem_preprocessor(project: Any, *, attach: bool = True, default_element_size: float | None = None) -> CadFemReadinessReport:
    """Build a CAD-FEM readiness snapshot and optionally attach it to the project."""

    index = build_topology_identity_index(project, attach=False)
    topology_rows = list(index.topology.values())
    topology_summary = index.summary()
    blockers: list[str] = []
    warnings: list[str] = []
    validation = validate_topology_identity_index(project, require_faces=True, require_edges=False)
    blockers.extend(str(item) for item in list(validation.get("blockers", []) or []))

    if topology_summary.get("solid_count", 0) <= 0:
        blockers.append("No solid topology identities are available for volume meshing.")
    if topology_summary.get("face_count", 0) <= 0:
        blockers.append("No face topology identities are available for boundary conditions or surface physical groups.")

    mats = _material_ids(project)
    material_gaps: list[str] = []
    for item in topology_rows:
        if item.kind == "solid":
            if not item.material_id:
                material_gaps.append(item.id)
            elif mats and item.material_id not in mats:
                material_gaps.append(item.id)
    if material_gaps:
        blockers.append(f"Solid topology records without valid material assignment: {material_gaps[:5]}.")

    project_bbox = _project_bounds(project, topology_rows)
    candidates = _boundary_candidates(topology_rows, project_bbox)
    groups = _physical_groups(topology_rows)
    controls = _mesh_controls(topology_rows, element_size=_mesh_size(project, default_element_size))
    roles = {item.candidate_role for item in candidates}
    if "fixed_base" not in roles:
        warnings.append("No bottom fixed-base face candidate was inferred; user should pick or define displacement supports before solving.")
    if "roller_side" not in roles:
        warnings.append("No side roller face candidate was inferred; lateral constraints may need manual assignment.")
    if "load_or_free_surface" not in roles:
        warnings.append("No top free/load face candidate was inferred; surface loads may require manual selection.")

    solver_requirements = _solver_requirements(project, mesh_controls=controls)
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    if mesh is None:
        warnings.append("No finite-element mesh is attached yet; this report is ready for meshing, not solving.")
    elif int(getattr(mesh, "cell_count", 0) or 0) <= 0:
        blockers.append("Attached mesh has no cells.")

    status = "ready_for_meshing" if not blockers and mesh is None else "ready_for_solve_precheck" if not blockers else "blocked"
    report = CadFemReadinessReport(
        ok=not blockers,
        status=status,
        blockers=blockers,
        warnings=warnings,
        physical_groups=groups,
        boundary_candidates=candidates,
        mesh_controls=controls,
        topology_summary=topology_summary,
        solver_requirements=solver_requirements,
        metadata={
            "project_bounds": list(project_bbox) if project_bbox is not None else None,
            "topology_identity_validation": validation,
            "mesh_size_source": "argument" if default_element_size is not None else "project.mesh_model.mesh_settings.global_size",
        },
    )
    if attach:
        payload = report.to_dict()
        try:
            project.metadata["cad_fem_preprocessor"] = payload
        except Exception:
            pass
        try:
            project.cad_shape_store.metadata["cad_fem_preprocessor"] = payload
        except Exception:
            pass
        try:
            for control in controls:
                if control.element_size is not None:
                    project.mesh_model.mesh_settings.local_size_fields[control.target_key] = float(control.element_size)
            project.mesh_model.mesh_settings.metadata["cad_fem_preprocessor_contract"] = CAD_FEM_PREPROCESSOR_CONTRACT
        except Exception:
            pass
        try:
            project.mark_changed(["topology", "mesh", "solver"], action="build_cad_fem_preprocessor")
        except Exception:
            pass
    return report


def validate_cad_fem_preprocessor(project: Any, *, require_boundary_candidates: bool = True, require_mesh_controls: bool = True) -> dict[str, Any]:
    report = build_cad_fem_preprocessor(project, attach=False)
    blockers = list(report.blockers)
    if require_boundary_candidates and not report.boundary_candidates:
        blockers.append("No CAD-FEM boundary candidates are available.")
    if require_mesh_controls and not report.mesh_controls:
        blockers.append("No CAD-FEM mesh controls are available.")
    return {
        "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
        "ok": not blockers,
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "warnings": list(report.warnings),
        "summary": report.summary(),
        "topology_summary": dict(report.topology_summary),
    }


__all__ = ["build_cad_fem_preprocessor", "validate_cad_fem_preprocessor"]
