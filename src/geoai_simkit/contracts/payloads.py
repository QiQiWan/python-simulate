from __future__ import annotations

"""Typed payload envelopes used at module and plugin boundaries.

These contracts intentionally avoid importing implementation objects.  They give
workflow reports, external plugin loading, quality gates and solver routing a
stable shape that can be serialized, rendered in GUI tables, and validated by
architecture tests.
"""

from dataclasses import dataclass, field
from typing import Mapping

JsonScalar = str | int | float | bool | None
JsonMap = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class WorkflowArtifactPayload:
    """Serializable payload summary for one workflow artifact."""

    artifact_id: str
    key: str
    kind: str
    producer: str
    payload_type: str = "unknown"
    status: str = "ok"
    accepted: bool = True
    summary: JsonMap = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "key": self.key,
            "kind": self.kind,
            "producer": self.producer,
            "payload_type": self.payload_type,
            "status": self.status,
            "accepted": bool(self.accepted),
            "summary": dict(self.summary),
            "diagnostics": list(self.diagnostics),
            "metadata": {"contract": "workflow_artifact_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class PluginRegistrationPayload:
    """Serializable description of a plugin registration request or result."""

    group: str
    registry_key: str
    category: str
    plugin_key: str
    entry_point: str = ""
    replace: bool = False
    source: str = "internal"
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "registry_key": self.registry_key,
            "category": self.category,
            "plugin_key": self.plugin_key,
            "entry_point": self.entry_point,
            "replace": bool(self.replace),
            "source": self.source,
            "metadata": {"contract": "plugin_registration_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class MeshPayload:
    """Typed mesh summary for workflow and quality-gate boundaries."""

    mesh_kind: str = "unknown"
    node_count: int = 0
    cell_count: int = 0
    cell_families: tuple[str, ...] = ()
    solid_cell_count: int = 0
    surface_cell_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "mesh_kind": self.mesh_kind,
            "node_count": int(self.node_count),
            "cell_count": int(self.cell_count),
            "cell_families": list(self.cell_families),
            "solid_cell_count": int(self.solid_cell_count),
            "surface_cell_count": int(self.surface_cell_count),
            "metadata": {"contract": "mesh_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class SolverInputPayload:
    """Typed solver input summary without leaking concrete model objects."""

    backend: str
    stage_count: int = 0
    active_cell_count: int = 0
    material_count: int = 0
    has_boundary_conditions: bool = False
    has_loads: bool = False
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "stage_count": int(self.stage_count),
            "active_cell_count": int(self.active_cell_count),
            "material_count": int(self.material_count),
            "has_boundary_conditions": bool(self.has_boundary_conditions),
            "has_loads": bool(self.has_loads),
            "metadata": {"contract": "solver_input_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class SolverOutputPayload:
    """Typed solver output summary for workflow artifacts and reports."""

    backend: str
    accepted: bool
    status: str = "ok"
    stage_count: int = 0
    result_field_count: int = 0
    metrics: JsonMap = field(default_factory=dict)
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "accepted": bool(self.accepted),
            "status": self.status,
            "stage_count": int(self.stage_count),
            "result_field_count": int(self.result_field_count),
            "metrics": dict(self.metrics),
            "metadata": {"contract": "solver_output_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class MaterialMappingPayload:
    """Typed material-region mapping summary."""

    region_count: int = 0
    material_count: int = 0
    unmapped_region_count: int = 0
    missing_material_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "region_count": int(self.region_count),
            "material_count": int(self.material_count),
            "unmapped_region_count": int(self.unmapped_region_count),
            "missing_material_count": int(self.missing_material_count),
            "metadata": {"contract": "material_mapping_payload_v1", **dict(self.metadata)},
        }


@dataclass(frozen=True, slots=True)
class QualityGatePayload:
    """Typed quality-gate summary shared by workflow and GUI layers."""

    gate: str
    ok: bool
    blocking_issue_count: int = 0
    warning_count: int = 0
    checked_entity_count: int = 0
    metadata: JsonMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "gate": self.gate,
            "ok": bool(self.ok),
            "blocking_issue_count": int(self.blocking_issue_count),
            "warning_count": int(self.warning_count),
            "checked_entity_count": int(self.checked_entity_count),
            "metadata": {"contract": "quality_gate_payload_v1", **dict(self.metadata)},
        }


__all__ = [
    "JsonMap",
    "JsonScalar",
    "MaterialMappingPayload",
    "MeshPayload",
    "PluginRegistrationPayload",
    "QualityGatePayload",
    "SolverInputPayload",
    "SolverOutputPayload",
    "WorkflowArtifactPayload",
]
