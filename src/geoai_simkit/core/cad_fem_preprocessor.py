from __future__ import annotations

"""Dependency-light CAD to FEM preprocessor contracts.

These records describe the engineering information that must be available after
CAD interaction and before meshing/solving: physical groups, topology-level
boundary/load candidates, local mesh controls and readiness diagnostics.  The
module deliberately avoids Qt, PyVista, VTK, OCC, IfcOpenShell, Gmsh and solver
imports so both GUI and headless services can share the same payload.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

CAD_FEM_PREPROCESSOR_CONTRACT = "geoai_simkit_cad_fem_preprocessor_v1"


def _meta(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _ls(value: Any) -> list[str]:
    return [str(item) for item in list(value or []) if str(item)]


@dataclass(frozen=True, slots=True)
class CadFemPhysicalGroup:
    """Physical group planned for Gmsh/meshio/solver hand-off."""

    id: str
    name: str
    dimension: int
    topology_keys: list[str] = field(default_factory=list)
    source_entity_ids: list[str] = field(default_factory=list)
    material_id: str = ""
    phase_ids: list[str] = field(default_factory=list)
    role: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
            "id": self.id,
            "name": self.name,
            "dimension": int(self.dimension),
            "topology_keys": list(self.topology_keys),
            "source_entity_ids": list(self.source_entity_ids),
            "material_id": self.material_id,
            "phase_ids": list(self.phase_ids),
            "role": self.role,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CadFemPhysicalGroup":
        d = dict(data or {})
        return cls(
            id=str(d.get("id") or "physical_group"),
            name=str(d.get("name") or d.get("id") or "physical_group"),
            dimension=int(d.get("dimension", 3) or 3),
            topology_keys=_ls(d.get("topology_keys")),
            source_entity_ids=_ls(d.get("source_entity_ids")),
            material_id=str(d.get("material_id") or ""),
            phase_ids=_ls(d.get("phase_ids")),
            role=str(d.get("role") or ""),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class CadFemBoundaryCandidate:
    """Topology-level candidate for BC, load, interface or excavation semantics."""

    id: str
    topology_key: str
    topology_id: str
    shape_id: str
    topology_kind: str = "face"
    source_entity_id: str = ""
    candidate_role: str = "unknown"
    dimension: int = 2
    normal_axis: str = ""
    bounds: tuple[float, float, float, float, float, float] | None = None
    material_id: str = ""
    phase_ids: list[str] = field(default_factory=list)
    physical_group_id: str = ""
    confidence: str = "derived"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
            "id": self.id,
            "topology_key": self.topology_key,
            "topology_id": self.topology_id,
            "shape_id": self.shape_id,
            "topology_kind": self.topology_kind,
            "source_entity_id": self.source_entity_id,
            "candidate_role": self.candidate_role,
            "dimension": int(self.dimension),
            "normal_axis": self.normal_axis,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "material_id": self.material_id,
            "phase_ids": list(self.phase_ids),
            "physical_group_id": self.physical_group_id,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CadFemBoundaryCandidate":
        d = dict(data or {})
        bounds = d.get("bounds")
        return cls(
            id=str(d.get("id") or "boundary_candidate"),
            topology_key=str(d.get("topology_key") or ""),
            topology_id=str(d.get("topology_id") or ""),
            shape_id=str(d.get("shape_id") or ""),
            topology_kind=str(d.get("topology_kind") or "face"),
            source_entity_id=str(d.get("source_entity_id") or ""),
            candidate_role=str(d.get("candidate_role") or "unknown"),
            dimension=int(d.get("dimension", 2) or 2),
            normal_axis=str(d.get("normal_axis") or ""),
            bounds=None if bounds is None else tuple(float(v) for v in list(bounds)[:6]),  # type: ignore[arg-type]
            material_id=str(d.get("material_id") or ""),
            phase_ids=_ls(d.get("phase_ids")),
            physical_group_id=str(d.get("physical_group_id") or ""),
            confidence=str(d.get("confidence") or "derived"),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class CadFemMeshControl:
    """Local mesh control derived from CAD topology and user intent."""

    id: str
    target_key: str
    target_kind: str = "solid"
    element_size: float | None = None
    growth_rate: float | None = None
    priority: int = 0
    method: str = "tet4"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
            "id": self.id,
            "target_key": self.target_key,
            "target_kind": self.target_kind,
            "element_size": self.element_size,
            "growth_rate": self.growth_rate,
            "priority": int(self.priority),
            "method": self.method,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CadFemMeshControl":
        d = dict(data or {})
        size = d.get("element_size")
        growth = d.get("growth_rate")
        return cls(
            id=str(d.get("id") or "mesh_control"),
            target_key=str(d.get("target_key") or ""),
            target_kind=str(d.get("target_kind") or "solid"),
            element_size=None if size is None else float(size),
            growth_rate=None if growth is None else float(growth),
            priority=int(d.get("priority", 0) or 0),
            method=str(d.get("method") or "tet4"),
            reason=str(d.get("reason") or ""),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class CadFemReadinessReport:
    """CAD-FEM readiness payload for GUI panels and batch gates."""

    ok: bool = False
    status: str = "not_built"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    physical_groups: list[CadFemPhysicalGroup] = field(default_factory=list)
    boundary_candidates: list[CadFemBoundaryCandidate] = field(default_factory=list)
    mesh_controls: list[CadFemMeshControl] = field(default_factory=list)
    topology_summary: dict[str, Any] = field(default_factory=dict)
    solver_requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def contract(self) -> str:
        return CAD_FEM_PREPROCESSOR_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CAD_FEM_PREPROCESSOR_CONTRACT,
            "ok": bool(self.ok),
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "physical_groups": [item.to_dict() for item in self.physical_groups],
            "boundary_candidates": [item.to_dict() for item in self.boundary_candidates],
            "mesh_controls": [item.to_dict() for item in self.mesh_controls],
            "topology_summary": dict(self.topology_summary),
            "solver_requirements": dict(self.solver_requirements),
            "summary": self.summary(),
            "metadata": dict(self.metadata),
        }

    def summary(self) -> dict[str, Any]:
        roles: dict[str, int] = {}
        for item in self.boundary_candidates:
            roles[item.candidate_role] = roles.get(item.candidate_role, 0) + 1
        return {
            "physical_group_count": len(self.physical_groups),
            "boundary_candidate_count": len(self.boundary_candidates),
            "mesh_control_count": len(self.mesh_controls),
            "candidate_roles": roles,
            "blocker_count": len(self.blockers),
            "warning_count": len(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "CadFemReadinessReport":
        d = dict(data or {})
        return cls(
            ok=bool(d.get("ok", False)),
            status=str(d.get("status") or "not_built"),
            blockers=_ls(d.get("blockers")),
            warnings=_ls(d.get("warnings")),
            physical_groups=[CadFemPhysicalGroup.from_dict(x) for x in list(d.get("physical_groups", []) or [])],
            boundary_candidates=[CadFemBoundaryCandidate.from_dict(x) for x in list(d.get("boundary_candidates", []) or [])],
            mesh_controls=[CadFemMeshControl.from_dict(x) for x in list(d.get("mesh_controls", []) or [])],
            topology_summary=dict(d.get("topology_summary", {}) or {}),
            solver_requirements=dict(d.get("solver_requirements", {}) or {}),
            metadata=dict(d.get("metadata", {}) or {}),
        )


__all__ = [
    "CAD_FEM_PREPROCESSOR_CONTRACT",
    "CadFemBoundaryCandidate",
    "CadFemMeshControl",
    "CadFemPhysicalGroup",
    "CadFemReadinessReport",
]
