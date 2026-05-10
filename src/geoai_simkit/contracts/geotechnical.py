from __future__ import annotations

"""Strict geotechnical Project Port v2 DTOs.

These helpers expose production-facing engineering state without leaking the
legacy ``GeoProjectDocument`` object through GUI/services. They are intentionally
plain dataclasses and use only dependency-light contracts.
"""

from dataclasses import dataclass, field
from typing import Mapping

from .mesh import SOLID_CELL_TYPES, SURFACE_CELL_TYPES
from .project import (
    ProjectReadPort,
    project_document_from,
    project_mesh_summary,
    project_stage_summary,
)


def _as_dict(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        try:
            return dict(value.to_dict())
        except Exception:
            return {}
    out: dict[str, object] = {}
    for key in ("id", "name", "kind", "dof", "value", "target_ids", "stage_ids", "material_id", "contact_mode", "components", "metadata"):
        if hasattr(value, key):
            out[key] = getattr(value, key)
    return out


def _project(value: ProjectReadPort | object) -> object:
    return project_document_from(value)


def _mesh(value: ProjectReadPort | object) -> object:
    current_mesh = getattr(value, "current_mesh", None)
    if callable(current_mesh):
        try:
            return current_mesh()
        except Exception:
            pass
    doc = _project(value)
    mesh_model = getattr(doc, "mesh_model", None)
    return getattr(mesh_model, "mesh_document", None)


def _sorted_unique(values: object) -> tuple[str, ...]:
    try:
        iterable = list(values or [])
    except TypeError:
        iterable = []
    return tuple(sorted({str(item) for item in iterable if str(item) != ""}))


def _material_ids_from_library(project: object) -> tuple[str, ...]:
    library = getattr(project, "material_library", None)
    if library is None:
        return ()
    ids: set[str] = set()
    material_ids = getattr(library, "material_ids", None)
    if callable(material_ids):
        try:
            ids.update(str(item) for item in material_ids())
        except Exception:
            pass
    for attr in ("soil_materials", "plate_materials", "beam_materials", "interface_materials"):
        value = getattr(library, attr, None)
        if isinstance(value, Mapping):
            ids.update(str(key) for key in value)
    return tuple(sorted(ids))


def _solver_model(project: object) -> object:
    return getattr(project, "solver_model", None)


def _structure_model(project: object) -> object:
    return getattr(project, "structure_model", None)


@dataclass(frozen=True, slots=True)
class SolidMeshSummary:
    has_mesh: bool = False
    node_count: int = 0
    cell_count: int = 0
    volume_cell_count: int = 0
    surface_cell_count: int = 0
    cell_families: tuple[str, ...] = ()
    block_ids: tuple[str, ...] = ()
    region_names: tuple[str, ...] = ()
    material_ids: tuple[str, ...] = ()
    mesh_role: str = "unknown"
    mesh_dimension: int = 0
    solid_solver_ready: bool = False
    quality_metrics: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "has_mesh": bool(self.has_mesh),
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "volume_cell_count": int(self.volume_cell_count),
            "surface_cell_count": int(self.surface_cell_count),
            "cell_families": list(self.cell_families),
            "block_ids": list(self.block_ids),
            "region_names": list(self.region_names),
            "material_ids": list(self.material_ids),
            "mesh_role": self.mesh_role,
            "mesh_dimension": int(self.mesh_dimension),
            "solid_solver_ready": bool(self.solid_solver_ready),
            "quality_metrics": dict(self.quality_metrics),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MaterialMappingSummary:
    ok: bool = False
    library_material_ids: tuple[str, ...] = ()
    mesh_material_ids: tuple[str, ...] = ()
    missing_material_ids: tuple[str, ...] = ()
    unused_material_ids: tuple[str, ...] = ()
    unmapped_cell_count: int = 0
    region_material_map: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "library_material_ids": list(self.library_material_ids),
            "mesh_material_ids": list(self.mesh_material_ids),
            "missing_material_ids": list(self.missing_material_ids),
            "unused_material_ids": list(self.unused_material_ids),
            "unmapped_cell_count": int(self.unmapped_cell_count),
            "region_material_map": dict(self.region_material_map),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BoundaryConditionSummary:
    boundary_condition_count: int = 0
    constrained_dof_count: int = 0
    target_count: int = 0
    stage_ids: tuple[str, ...] = ()
    has_constraints: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "boundary_condition_count": int(self.boundary_condition_count),
            "constrained_dof_count": int(self.constrained_dof_count),
            "target_count": int(self.target_count),
            "stage_ids": list(self.stage_ids),
            "has_constraints": bool(self.has_constraints),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class LoadSummary:
    load_count: int = 0
    surface_load_count: int = 0
    body_force_count: int = 0
    nodal_load_count: int = 0
    stage_ids: tuple[str, ...] = ()
    has_loads: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "load_count": int(self.load_count),
            "surface_load_count": int(self.surface_load_count),
            "body_force_count": int(self.body_force_count),
            "nodal_load_count": int(self.nodal_load_count),
            "stage_ids": list(self.stage_ids),
            "has_loads": bool(self.has_loads),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class InterfaceSummary:
    interface_count: int = 0
    interface_material_ids: tuple[str, ...] = ()
    missing_material_ids: tuple[str, ...] = ()
    contact_modes: tuple[str, ...] = ()
    candidate_count: int = 0
    contact_ready: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "interface_count": int(self.interface_count),
            "interface_material_ids": list(self.interface_material_ids),
            "missing_material_ids": list(self.missing_material_ids),
            "contact_modes": list(self.contact_modes),
            "candidate_count": int(self.candidate_count),
            "contact_ready": bool(self.contact_ready),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StageActivationSummary:
    stage_ids: tuple[str, ...] = ()
    active_block_ids_by_stage: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    active_cell_counts_by_stage: Mapping[str, int] = field(default_factory=dict)
    active_interface_counts_by_stage: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_ids": list(self.stage_ids),
            "active_block_ids_by_stage": {key: list(value) for key, value in self.active_block_ids_by_stage.items()},
            "active_cell_counts_by_stage": {key: int(value) for key, value in self.active_cell_counts_by_stage.items()},
            "active_interface_counts_by_stage": {key: int(value) for key, value in self.active_interface_counts_by_stage.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AnalysisReadinessSummary:
    ready: bool = False
    solid_mesh_ready: bool = False
    material_mapping_ready: bool = False
    boundary_conditions_ready: bool = False
    loads_ready: bool = False
    interfaces_ready: bool = True
    blocking_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": bool(self.ready),
            "solid_mesh_ready": bool(self.solid_mesh_ready),
            "material_mapping_ready": bool(self.material_mapping_ready),
            "boundary_conditions_ready": bool(self.boundary_conditions_ready),
            "loads_ready": bool(self.loads_ready),
            "interfaces_ready": bool(self.interfaces_ready),
            "blocking_issues": list(self.blocking_issues),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def solid_mesh_summary(project_or_port: ProjectReadPort | object) -> SolidMeshSummary:
    mesh = _mesh(project_or_port)
    base = project_mesh_summary(project_or_port)
    if mesh is None:
        return SolidMeshSummary(metadata={"project_mesh_summary": base.to_dict()})
    metadata = dict(getattr(mesh, "metadata", {}) or {})
    cell_types = tuple(str(item).lower() for item in list(getattr(mesh, "cell_types", []) or []))
    solid_count = sum(1 for item in cell_types if item in SOLID_CELL_TYPES)
    surface_count = sum(1 for item in cell_types if item in SURFACE_CELL_TYPES)
    cell_tags = dict(getattr(mesh, "cell_tags", {}) or {})
    quality = dict(metadata.get("quality_metrics", {}) or {})
    return SolidMeshSummary(
        has_mesh=True,
        node_count=int(getattr(mesh, "node_count", 0) or 0),
        cell_count=int(getattr(mesh, "cell_count", len(getattr(mesh, "cells", []) or [])) or 0),
        volume_cell_count=int(solid_count),
        surface_cell_count=int(surface_count),
        cell_families=tuple(sorted(set(cell_types))),
        block_ids=_sorted_unique(cell_tags.get("block_id", [])) or tuple(base.block_ids),
        region_names=_sorted_unique(cell_tags.get("region_name", [])),
        material_ids=_sorted_unique(cell_tags.get("material_id", [])),
        mesh_role=base.mesh_role,
        mesh_dimension=base.mesh_dimension,
        solid_solver_ready=bool(base.solid_solver_ready and solid_count > 0),
        quality_metrics=quality,
        metadata={**metadata, "project_mesh_summary": base.to_dict()},
    )


def material_mapping_summary(project_or_port: ProjectReadPort | object) -> MaterialMappingSummary:
    project = _project(project_or_port)
    mesh = _mesh(project_or_port)
    library_ids = _material_ids_from_library(project)
    mesh_material_ids: tuple[str, ...] = ()
    unmapped = 0
    region_map: dict[str, str] = {}
    if mesh is not None:
        tags = dict(getattr(mesh, "cell_tags", {}) or {})
        mats = [str(item) for item in list(tags.get("material_id", []) or [])]
        regions = [str(item) for item in list(tags.get("region_name", []) or [])]
        mesh_material_ids = _sorted_unique(mats)
        unmapped = sum(1 for item in mats if not item)
        for idx, region in enumerate(regions):
            mat = mats[idx] if idx < len(mats) else ""
            if region and mat:
                region_map.setdefault(region, mat)
    missing = tuple(sorted(set(mesh_material_ids) - set(library_ids)))
    unused = tuple(sorted(set(library_ids) - set(mesh_material_ids)))
    ok = bool(not missing and unmapped == 0 and (mesh_material_ids or not solid_mesh_summary(project_or_port).has_mesh))
    return MaterialMappingSummary(
        ok=ok,
        library_material_ids=library_ids,
        mesh_material_ids=mesh_material_ids,
        missing_material_ids=missing,
        unused_material_ids=unused,
        unmapped_cell_count=unmapped,
        region_material_map=region_map,
        metadata={"library_count": len(library_ids), "mesh_material_count": len(mesh_material_ids)},
    )


def boundary_condition_summary(project_or_port: ProjectReadPort | object) -> BoundaryConditionSummary:
    project = _project(project_or_port)
    solver_model = _solver_model(project)
    rows = dict(getattr(solver_model, "boundary_conditions", {}) or {}) if solver_model is not None else {}
    dof_count = 0
    targets: set[str] = set()
    stages: set[str] = set()
    for value in rows.values():
        row = _as_dict(value)
        dof_tokens = [token.strip() for token in str(row.get("dof", "")).replace(";", ",").split(",") if token.strip()]
        dof_count += max(len(dof_tokens), 1)
        targets.update(str(item) for item in list(row.get("target_ids", []) or []))
        stages.update(str(item) for item in list(row.get("stage_ids", []) or []))
    return BoundaryConditionSummary(
        boundary_condition_count=len(rows),
        constrained_dof_count=dof_count,
        target_count=len(targets),
        stage_ids=tuple(sorted(stages)),
        has_constraints=bool(rows and dof_count > 0),
        metadata={"boundary_condition_ids": sorted(str(key) for key in rows)},
    )


def load_summary(project_or_port: ProjectReadPort | object) -> LoadSummary:
    project = _project(project_or_port)
    solver_model = _solver_model(project)
    rows = dict(getattr(solver_model, "loads", {}) or {}) if solver_model is not None else {}
    surface = body = nodal = 0
    stages: set[str] = set()
    for value in rows.values():
        row = _as_dict(value)
        kind = str(row.get("kind", "surface_load")).lower()
        if "body" in kind or "gravity" in kind:
            body += 1
        elif "nodal" in kind or "point" in kind:
            nodal += 1
        else:
            surface += 1
        stages.update(str(item) for item in list(row.get("stage_ids", []) or []))
    return LoadSummary(
        load_count=len(rows),
        surface_load_count=surface,
        body_force_count=body,
        nodal_load_count=nodal,
        stage_ids=tuple(sorted(stages)),
        has_loads=bool(rows),
        metadata={"load_ids": sorted(str(key) for key in rows)},
    )


def interface_summary(project_or_port: ProjectReadPort | object) -> InterfaceSummary:
    project = _project(project_or_port)
    structures = _structure_model(project)
    rows = dict(getattr(structures, "structural_interfaces", {}) or {}) if structures is not None else {}
    library = getattr(project, "material_library", None)
    known = set(str(key) for key in dict(getattr(library, "interface_materials", {}) or {}).keys()) if library is not None else set()
    material_ids: set[str] = set()
    modes: set[str] = set()
    for value in rows.values():
        row = _as_dict(value)
        if row.get("material_id"):
            material_ids.add(str(row["material_id"]))
        modes.add(str(row.get("contact_mode", "frictional")))
    missing = tuple(sorted(material_ids - known))
    metadata = dict(getattr(project, "metadata", {}) or {})
    candidates = metadata.get("interface_candidates", metadata.get("multi_region_interfaces", []))
    candidate_count = len(list(candidates or [])) if not isinstance(candidates, Mapping) else len(candidates)
    return InterfaceSummary(
        interface_count=len(rows),
        interface_material_ids=tuple(sorted(material_ids)),
        missing_material_ids=missing,
        contact_modes=tuple(sorted(modes)),
        candidate_count=int(candidate_count),
        contact_ready=not missing,
        metadata={"interface_ids": sorted(str(key) for key in rows)},
    )


def stage_activation_summary(project_or_port: ProjectReadPort | object) -> StageActivationSummary:
    project = _project(project_or_port)
    stages = project_stage_summary(project_or_port)
    solver_model = _solver_model(project)
    compiled = dict(getattr(solver_model, "compiled_phase_models", {}) or {}) if solver_model is not None else {}
    active_cell_counts: dict[str, int] = {}
    active_interface_counts: dict[str, int] = {}
    for stage_id in stages.stage_ids:
        row = compiled.get(stage_id) or compiled.get(f"compiled_{stage_id}")
        active_cell_counts[stage_id] = int(getattr(row, "active_cell_count", 0) or 0) if row is not None else 0
        active_interface_counts[stage_id] = int(getattr(row, "interface_count", 0) or 0) if row is not None else 0
    return StageActivationSummary(
        stage_ids=stages.stage_ids,
        active_block_ids_by_stage=dict(stages.active_blocks_by_stage),
        active_cell_counts_by_stage=active_cell_counts,
        active_interface_counts_by_stage=active_interface_counts,
        metadata=dict(stages.metadata),
    )


def analysis_readiness_summary(project_or_port: ProjectReadPort | object) -> AnalysisReadinessSummary:
    mesh = solid_mesh_summary(project_or_port)
    mapping = material_mapping_summary(project_or_port)
    bcs = boundary_condition_summary(project_or_port)
    loads = load_summary(project_or_port)
    interfaces = interface_summary(project_or_port)
    blocking: list[str] = []
    warnings: list[str] = []
    if not mesh.solid_solver_ready:
        blocking.append("mesh.not_solid_solver_ready")
    if not mapping.ok:
        blocking.append("material.mapping_incomplete")
    if not bcs.has_constraints:
        blocking.append("boundary_conditions.missing_constraints")
    if not interfaces.contact_ready:
        blocking.append("interfaces.missing_materials")
    if not loads.has_loads:
        warnings.append("loads.none_defined")
    ready = not blocking
    return AnalysisReadinessSummary(
        ready=ready,
        solid_mesh_ready=mesh.solid_solver_ready,
        material_mapping_ready=mapping.ok,
        boundary_conditions_ready=bcs.has_constraints,
        loads_ready=loads.has_loads,
        interfaces_ready=interfaces.contact_ready,
        blocking_issues=tuple(blocking),
        warnings=tuple(warnings),
        metadata={
            "solid_mesh": mesh.to_dict(),
            "material_mapping": mapping.to_dict(),
            "boundary_conditions": bcs.to_dict(),
            "loads": loads.to_dict(),
            "interfaces": interfaces.to_dict(),
        },
    )


__all__ = [
    "AnalysisReadinessSummary",
    "BoundaryConditionSummary",
    "InterfaceSummary",
    "LoadSummary",
    "MaterialMappingSummary",
    "SolidMeshSummary",
    "StageActivationSummary",
    "analysis_readiness_summary",
    "boundary_condition_summary",
    "interface_summary",
    "load_summary",
    "material_mapping_summary",
    "solid_mesh_summary",
    "stage_activation_summary",
]
