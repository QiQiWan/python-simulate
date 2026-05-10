from __future__ import annotations

"""Stable project-document contracts and Project Port helpers.

Project ports are the canonical way for modules to exchange project state.  The
legacy ``GeoProjectDocument`` remains supported, but new facades and services
should prefer the typed summaries exposed here and unwrap concrete project
objects only at adapter boundaries.
"""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProjectPortCapabilities:
    """Capabilities exposed by a project port boundary."""

    readable: bool = True
    writable: bool = False
    transactional: bool = False
    legacy_document_access: bool = True
    schema_version: str = "geoproject_document_v1"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "readable": bool(self.readable),
            "writable": bool(self.writable),
            "transactional": bool(self.transactional),
            "legacy_document_access": bool(self.legacy_document_access),
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Small immutable summary of a project exchanged across module boundaries."""

    project_id: str
    name: str
    schema_version: str = "geoproject_document_v1"
    geometry_count: int = 0
    mesh_cell_count: int = 0
    mesh_node_count: int = 0
    stage_count: int = 0
    result_stage_count: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "schema_version": self.schema_version,
            "geometry_count": int(self.geometry_count),
            "mesh_cell_count": int(self.mesh_cell_count),
            "mesh_node_count": int(self.mesh_node_count),
            "stage_count": int(self.stage_count),
            "result_stage_count": int(self.result_stage_count),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectGeometrySummary:
    """Strict read DTO for geometry resources exposed by a project."""

    keys: tuple[str, ...] = ()
    volume_keys: tuple[str, ...] = ()
    surface_keys: tuple[str, ...] = ()
    block_keys: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def geometry_count(self) -> int:
        return len(self.keys)

    def to_dict(self) -> dict[str, object]:
        return {
            "keys": list(self.keys),
            "volume_keys": list(self.volume_keys),
            "surface_keys": list(self.surface_keys),
            "block_keys": list(self.block_keys),
            "geometry_count": self.geometry_count,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectMeshSummary:
    """Strict read DTO for the current mesh without leaking mesh internals."""

    has_mesh: bool = False
    node_count: int = 0
    cell_count: int = 0
    mesh_kind: str = "unknown"
    block_ids: tuple[str, ...] = ()
    mesh_role: str = "unknown"
    mesh_dimension: int = 0
    cell_families: tuple[str, ...] = ()
    solid_cell_count: int = 0
    surface_cell_count: int = 0
    solid_solver_ready: bool = False
    requires_volume_meshing: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "has_mesh": bool(self.has_mesh),
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "mesh_kind": self.mesh_kind,
            "block_ids": list(self.block_ids),
            "mesh_role": self.mesh_role,
            "mesh_dimension": int(self.mesh_dimension),
            "cell_families": list(self.cell_families),
            "solid_cell_count": int(self.solid_cell_count),
            "surface_cell_count": int(self.surface_cell_count),
            "solid_solver_ready": bool(self.solid_solver_ready),
            "requires_volume_meshing": bool(self.requires_volume_meshing),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectStageSummary:
    """Strict read DTO for stage / phase planning state."""

    stage_ids: tuple[str, ...] = ()
    active_blocks_by_stage: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def stage_count(self) -> int:
        return len(self.stage_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_ids": list(self.stage_ids),
            "stage_count": self.stage_count,
            "active_blocks_by_stage": {str(key): list(value) for key, value in self.active_blocks_by_stage.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectMaterialSummary:
    """Strict read DTO for material resources."""

    material_ids: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def material_count(self) -> int:
        return len(self.material_ids)

    def to_dict(self) -> dict[str, object]:
        return {"material_ids": list(self.material_ids), "material_count": self.material_count, "metadata": dict(self.metadata)}


@dataclass(frozen=True, slots=True)
class ProjectResultStoreSummary:
    """Strict read DTO for result-store state."""

    stage_ids: tuple[str, ...] = ()
    field_count: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def stage_count(self) -> int:
        return len(self.stage_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_ids": list(self.stage_ids),
            "stage_count": self.stage_count,
            "field_count": int(self.field_count),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectCompiledPhaseSummary:
    """Strict read DTO for compiled phase model availability."""

    phase_ids: tuple[str, ...] = ()
    phase_count: int = 0
    compiled: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "phase_ids": list(self.phase_ids),
            "phase_count": int(self.phase_count),
            "compiled": bool(self.compiled),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectResourceSummary:
    """Read-only summary of resources exposed by a Project Port."""

    geometry_keys: tuple[str, ...] = ()
    stage_ids: tuple[str, ...] = ()
    result_stage_ids: tuple[str, ...] = ()
    has_mesh: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_keys": list(self.geometry_keys),
            "stage_ids": list(self.stage_ids),
            "result_stage_ids": list(self.result_stage_ids),
            "has_mesh": bool(self.has_mesh),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectMutation:
    """A documented write operation requested by a module."""

    action: str
    channels: tuple[str, ...] = ()
    affected_entities: tuple[str, ...] = ()
    payload: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "channels": list(self.channels),
            "affected_entities": list(self.affected_entities),
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProjectTransaction:
    """A group of project mutations applied atomically by an adapter/service."""

    name: str
    mutations: tuple[ProjectMutation, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "mutations": [item.to_dict() for item in self.mutations], "metadata": dict(self.metadata)}


@runtime_checkable
class ProjectReadPort(Protocol):
    """Read-only project boundary used by modules that should not mutate state."""

    def snapshot(self) -> ProjectSnapshot: ...

    def resource_summary(self) -> ProjectResourceSummary: ...

    def get_project(self) -> object: ...

    def geometry_keys(self) -> tuple[str, ...]: ...

    def stage_ids(self) -> tuple[str, ...]: ...

    def result_stage_ids(self) -> tuple[str, ...]: ...

    def current_mesh(self) -> object: ...

    def geometry_summary(self) -> ProjectGeometrySummary: ...

    def mesh_summary(self) -> ProjectMeshSummary: ...

    def stage_summary(self) -> ProjectStageSummary: ...

    def material_summary(self) -> ProjectMaterialSummary: ...

    def result_store_summary(self) -> ProjectResultStoreSummary: ...

    def compiled_phase_summary(self) -> ProjectCompiledPhaseSummary: ...

    def port_capabilities(self) -> ProjectPortCapabilities: ...


@runtime_checkable
class ProjectWritePort(ProjectReadPort, Protocol):
    """Write boundary for services/adapters that apply documented mutations."""

    def apply_mutation(self, mutation: ProjectMutation) -> ProjectSnapshot: ...

    def apply_transaction(self, transaction: ProjectTransaction) -> ProjectSnapshot: ...

    def mark_changed(
        self,
        channels: tuple[str, ...] | list[str],
        *,
        action: str,
        affected_entities: tuple[str, ...] | list[str] = (),
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectSnapshot: ...


@runtime_checkable
class ProjectRepository(Protocol):
    """Persistence boundary for project documents."""

    def load(self, source: str | bytes | object) -> ProjectWritePort: ...

    def save(self, project: ProjectReadPort, target: str | bytes | object) -> None: ...


def is_project_port(value: object) -> bool:
    """Return True when *value* exposes the minimum project-port read API.

    The check intentionally remains backward compatible with 0.8.56 custom
    ports. Strict summary methods are accessed via helper fallbacks below.
    """

    required = ("snapshot", "resource_summary", "get_project", "geometry_keys", "stage_ids", "result_stage_ids", "current_mesh")
    return all(callable(getattr(value, name, None)) for name in required)


def project_document_from(project_or_port: object) -> object:
    """Unwrap a Project Port to its legacy project document at adapter boundary."""

    getter = getattr(project_or_port, "get_project", None)
    if callable(getter):
        return getter()
    return project_or_port


def project_port_capabilities(project_or_port: object) -> ProjectPortCapabilities:
    """Best-effort capability descriptor for a port or legacy project object."""

    getter = getattr(project_or_port, "port_capabilities", None)
    if callable(getter):
        capabilities = getter()
        if isinstance(capabilities, ProjectPortCapabilities):
            return capabilities
        if isinstance(capabilities, Mapping):
            return ProjectPortCapabilities(
                readable=bool(capabilities.get("readable", True)),
                writable=bool(capabilities.get("writable", False)),
                transactional=bool(capabilities.get("transactional", False)),
                legacy_document_access=bool(capabilities.get("legacy_document_access", True)),
                schema_version=str(capabilities.get("schema_version", "geoproject_document_v1")),
                metadata=dict(capabilities.get("metadata", {}) or {}),
            )
    return ProjectPortCapabilities(
        readable=True,
        writable=hasattr(project_or_port, "mark_changed"),
        transactional=hasattr(project_or_port, "mark_changed"),
        legacy_document_access=True,
        metadata={"source": "legacy_document" if not is_project_port(project_or_port) else "project_port"},
    )


def _mapping_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(str(key) for key in value.keys())
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return ()


def _call_summary(project_or_port: object, method_name: str, expected_type: type[object]) -> object | None:
    method = getattr(project_or_port, method_name, None)
    if callable(method):
        try:
            value = method()
        except TypeError:
            value = None
        if isinstance(value, expected_type):
            return value
        if isinstance(value, Mapping):
            try:
                return expected_type(**dict(value))
            except TypeError:
                return None
    return None


@dataclass(slots=True)
class ProjectContext:
    """Default Project Port implementation wrapping a legacy project object."""

    project: object
    metadata: dict[str, object] = field(default_factory=dict)

    def get_project(self) -> object:
        return self.project

    def geometry_keys(self) -> tuple[str, ...]:
        return self.geometry_summary().keys

    def stage_ids(self) -> tuple[str, ...]:
        return self.stage_summary().stage_ids

    def result_stage_ids(self) -> tuple[str, ...]:
        return self.result_store_summary().stage_ids

    def current_mesh(self) -> object:
        mesh_model = getattr(self.project, "mesh_model", None)
        return getattr(mesh_model, "mesh_document", None)

    def geometry_summary(self) -> ProjectGeometrySummary:
        geometry_model = getattr(self.project, "geometry_model", None)
        volumes = getattr(geometry_model, "volumes", {}) or {}
        surfaces = getattr(geometry_model, "surfaces", {}) or {}
        geometry_doc = getattr(geometry_model, "geometry_document", None)
        if geometry_doc is None:
            geometry_doc = getattr(self.project, "geometry", None)
        blocks = getattr(geometry_doc, "blocks", {}) or {}
        block_keys = _mapping_keys(blocks)
        volume_keys = _mapping_keys(volumes)
        surface_keys = _mapping_keys(surfaces)
        keys = tuple(sorted({*volume_keys, *surface_keys, *block_keys}))
        return ProjectGeometrySummary(keys=keys, volume_keys=volume_keys, surface_keys=surface_keys, block_keys=block_keys, metadata=dict(self.metadata))

    def mesh_summary(self) -> ProjectMeshSummary:
        mesh = self.current_mesh()
        if mesh is None:
            return ProjectMeshSummary(metadata=dict(self.metadata))
        block_ids_func = getattr(mesh, "block_ids", None)
        block_ids = tuple(str(item) for item in block_ids_func()) if callable(block_ids_func) else ()
        metadata = dict(getattr(mesh, "metadata", {}) or {})
        cell_types = tuple(str(item).lower() for item in list(getattr(mesh, "cell_types", []) or []))
        cell_families = tuple(sorted(set(cell_types)))
        solid_types = {"tet4", "tet4_preview", "tet10", "hex8", "hex8_preview", "hex20", "wedge6", "pyramid5"}
        surface_types = {"tri3", "quad4", "line2"}
        solid_count = sum(1 for item in cell_types if item in solid_types)
        surface_count = sum(1 for item in cell_types if item in surface_types)
        mesh_role = str(metadata.get("mesh_role") or ("solid_volume" if solid_count else ("geometry_surface" if surface_count else "unknown")))
        mesh_dimension = int(metadata.get("mesh_dimension") or (3 if solid_count else (2 if surface_count else 0)))
        solid_ready = bool(metadata.get("solid_solver_ready", bool(solid_count and mesh_dimension == 3)))
        requires_volume = bool(metadata.get("requires_volume_meshing", bool(surface_count and not solid_count)))
        return ProjectMeshSummary(
            has_mesh=True,
            node_count=int(getattr(mesh, "node_count", 0) or 0),
            cell_count=int(getattr(mesh, "cell_count", 0) or 0),
            mesh_kind=str(metadata.get("mesh_kind") or getattr(mesh, "mesh_kind", getattr(mesh, "kind", mesh.__class__.__name__))),
            block_ids=block_ids,
            mesh_role=mesh_role,
            mesh_dimension=mesh_dimension,
            cell_families=cell_families,
            solid_cell_count=int(solid_count),
            surface_cell_count=int(surface_count),
            solid_solver_ready=solid_ready,
            requires_volume_meshing=requires_volume,
            metadata={**metadata, **dict(self.metadata)},
        )

    def stage_summary(self) -> ProjectStageSummary:
        manager = getattr(self.project, "phase_manager", None)
        if manager is None:
            return ProjectStageSummary(metadata=dict(self.metadata))
        order = getattr(manager, "order", None)
        if order is not None:
            stage_ids = tuple(str(item) for item in order)
        else:
            stages = getattr(manager, "stages", None)
            if isinstance(stages, Mapping):
                stage_ids = tuple(str(key) for key in stages)
            else:
                construction_phases = getattr(manager, "construction_phases", None)
                if isinstance(construction_phases, Mapping):
                    initial = getattr(getattr(manager, "initial_phase", None), "id", None)
                    stage_ids = tuple([str(initial)] if initial else ()) + tuple(str(key) for key in construction_phases)
                elif stages:
                    stage_ids = tuple(str(item) for item in stages)
                else:
                    stage_ids = ()
        volumes = self.geometry_summary().volume_keys or self.geometry_summary().keys
        active_by_stage: dict[str, tuple[str, ...]] = {}
        active_blocks_for_stage = getattr(manager, "active_blocks_for_stage", None)
        if callable(active_blocks_for_stage):
            for stage_id in stage_ids:
                try:
                    active_by_stage[stage_id] = tuple(str(item) for item in active_blocks_for_stage(tuple(volumes), stage_id=stage_id))
                except Exception:
                    active_by_stage[stage_id] = tuple(volumes)
        return ProjectStageSummary(stage_ids=stage_ids, active_blocks_by_stage=active_by_stage, metadata=dict(self.metadata))

    def material_summary(self) -> ProjectMaterialSummary:
        material_ids: tuple[str, ...] = ()
        for attr in ("material_library", "materials", "material_model"):
            value = getattr(self.project, attr, None)
            if value is None:
                continue
            if isinstance(value, Mapping):
                material_ids = tuple(str(key) for key in value)
                break
            items = getattr(value, "materials", None)
            if isinstance(items, Mapping):
                material_ids = tuple(str(key) for key in items)
                break
            registry = getattr(value, "registry", None)
            if isinstance(registry, Mapping):
                material_ids = tuple(str(key) for key in registry)
                break
        return ProjectMaterialSummary(material_ids=material_ids, metadata=dict(self.metadata))

    def result_store_summary(self) -> ProjectResultStoreSummary:
        store = getattr(self.project, "result_store", None)
        if store is None:
            return ProjectResultStoreSummary(metadata=dict(self.metadata))
        phase_results = getattr(store, "phase_results", None)
        if isinstance(phase_results, Mapping):
            stage_ids = tuple(str(key) for key in phase_results)
            field_count = sum(len(getattr(value, "fields", {}) or {}) if not isinstance(value, Mapping) else len(value) for value in phase_results.values())
            return ProjectResultStoreSummary(stage_ids=stage_ids, field_count=int(field_count), metadata=dict(self.metadata))
        stages = getattr(store, "stages", {}) or {}
        stage_ids = _mapping_keys(stages)
        field_count = int(getattr(store, "field_count", 0) or 0)
        return ProjectResultStoreSummary(stage_ids=stage_ids, field_count=field_count, metadata=dict(self.metadata))

    def compiled_phase_summary(self) -> ProjectCompiledPhaseSummary:
        compile_fn = getattr(self.project, "compile_phase_models", None)
        phase_ids = self.stage_ids()
        if not callable(compile_fn):
            return ProjectCompiledPhaseSummary(phase_ids=phase_ids, phase_count=len(phase_ids), compiled=False, metadata=dict(self.metadata))
        return ProjectCompiledPhaseSummary(phase_ids=phase_ids, phase_count=len(phase_ids), compiled=True, metadata=dict(self.metadata))

    def resource_summary(self) -> ProjectResourceSummary:
        return ProjectResourceSummary(
            geometry_keys=self.geometry_keys(),
            stage_ids=self.stage_ids(),
            result_stage_ids=self.result_stage_ids(),
            has_mesh=self.mesh_summary().has_mesh,
            metadata=dict(self.metadata),
        )

    def snapshot(self) -> ProjectSnapshot:
        settings = getattr(self.project, "project_settings", None)
        geometry = self.geometry_summary()
        mesh = self.mesh_summary()
        stages = self.stage_summary()
        results = self.result_store_summary()
        return ProjectSnapshot(
            project_id=str(getattr(settings, "project_id", "geo-project")),
            name=str(getattr(settings, "name", "Untitled Geo Project")),
            geometry_count=geometry.geometry_count,
            mesh_cell_count=mesh.cell_count,
            mesh_node_count=mesh.node_count,
            stage_count=stages.stage_count,
            result_stage_count=results.stage_count,
            metadata={**dict(getattr(self.project, "metadata", {}) or {}), **dict(self.metadata)},
        )

    def port_capabilities(self) -> ProjectPortCapabilities:
        return ProjectPortCapabilities(readable=True, writable=True, transactional=True, legacy_document_access=True, metadata={"adapter": "ProjectContext"})

    def apply_mutation(self, mutation: ProjectMutation) -> ProjectSnapshot:
        if hasattr(self.project, "mark_changed"):
            self.project.mark_changed(list(mutation.channels), action=mutation.action, affected_entities=list(mutation.affected_entities))
        self.metadata.setdefault("mutations", []).append(mutation.to_dict())
        return self.snapshot()

    def mark_changed(
        self,
        channels: tuple[str, ...] | list[str],
        *,
        action: str,
        affected_entities: tuple[str, ...] | list[str] = (),
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectSnapshot:
        return self.apply_mutation(
            ProjectMutation(
                action=str(action),
                channels=tuple(str(item) for item in channels),
                affected_entities=tuple(str(item) for item in affected_entities),
                payload=dict(payload or {}),
                metadata=dict(metadata or {}),
            )
        )

    def apply_transaction(self, transaction: ProjectTransaction) -> ProjectSnapshot:
        for mutation in transaction.mutations:
            self.apply_mutation(mutation)
        self.metadata.setdefault("transactions", []).append(transaction.to_dict())
        return self.snapshot()


def project_geometry_summary(project_or_port: object) -> ProjectGeometrySummary:
    value = _call_summary(project_or_port, "geometry_summary", ProjectGeometrySummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).geometry_summary()


def project_mesh_summary(project_or_port: object) -> ProjectMeshSummary:
    value = _call_summary(project_or_port, "mesh_summary", ProjectMeshSummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).mesh_summary()


def project_stage_summary(project_or_port: object) -> ProjectStageSummary:
    value = _call_summary(project_or_port, "stage_summary", ProjectStageSummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).stage_summary()


def project_material_summary(project_or_port: object) -> ProjectMaterialSummary:
    value = _call_summary(project_or_port, "material_summary", ProjectMaterialSummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).material_summary()


def project_result_store_summary(project_or_port: object) -> ProjectResultStoreSummary:
    value = _call_summary(project_or_port, "result_store_summary", ProjectResultStoreSummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).result_store_summary()


def project_compiled_phase_summary(project_or_port: object) -> ProjectCompiledPhaseSummary:
    value = _call_summary(project_or_port, "compiled_phase_summary", ProjectCompiledPhaseSummary)
    if value is not None:
        return value
    return ProjectContext(project_document_from(project_or_port)).compiled_phase_summary()


__all__ = [
    "ProjectCompiledPhaseSummary",
    "ProjectContext",
    "ProjectGeometrySummary",
    "ProjectMaterialSummary",
    "ProjectMeshSummary",
    "ProjectMutation",
    "ProjectPortCapabilities",
    "ProjectReadPort",
    "ProjectRepository",
    "ProjectResourceSummary",
    "ProjectResultStoreSummary",
    "ProjectSnapshot",
    "ProjectStageSummary",
    "ProjectTransaction",
    "ProjectWritePort",
    "is_project_port",
    "project_compiled_phase_summary",
    "project_document_from",
    "project_geometry_summary",
    "project_material_summary",
    "project_mesh_summary",
    "project_port_capabilities",
    "project_result_store_summary",
    "project_stage_summary",
]
