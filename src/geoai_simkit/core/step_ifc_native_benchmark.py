from __future__ import annotations

"""Dependency-light STEP/IFC native benchmark contracts for P8.5.

The records in this module are intentionally independent from Qt, PyVista,
OCC, IfcOpenShell, Gmsh and meshio.  They describe the evidence produced by a
real-file CAD certification run: native import capability, topology identity
coverage, persistent-name stability, physical groups, lineage readiness, mesh
entity mapping and solver-region mapping.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

STEP_IFC_NATIVE_BENCHMARK_CONTRACT = "geoai_simkit_step_ifc_native_benchmark_p85_v1"


def _ls(value: Any) -> list[str]:
    return [str(item) for item in list(value or []) if str(item)]


def _meta(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True, slots=True)
class StepIfcBenchmarkCaseSpec:
    """File-driven benchmark case specification."""

    source_path: str
    case_id: str = ""
    category: str = "real_step_ifc"
    require_native: bool | None = None
    expected_min_solids: int = 1
    expected_min_faces: int = 1
    expected_min_edges: int = 0
    require_physical_groups: bool = True
    require_solver_region_map: bool = True
    require_mesh_entity_map: bool = True
    require_lineage: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
            "case_id": self.case_id,
            "source_path": self.source_path,
            "category": self.category,
            "require_native": self.require_native,
            "expected_min_solids": int(self.expected_min_solids),
            "expected_min_faces": int(self.expected_min_faces),
            "expected_min_edges": int(self.expected_min_edges),
            "require_physical_groups": bool(self.require_physical_groups),
            "require_solver_region_map": bool(self.require_solver_region_map),
            "require_mesh_entity_map": bool(self.require_mesh_entity_map),
            "require_lineage": bool(self.require_lineage),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "StepIfcBenchmarkCaseSpec":
        d = dict(data or {})
        return cls(
            source_path=str(d.get("source_path") or d.get("path") or d.get("file") or ""),
            case_id=str(d.get("case_id") or d.get("id") or d.get("name") or ""),
            category=str(d.get("category") or "real_step_ifc"),
            require_native=None if d.get("require_native") is None else bool(d.get("require_native")),
            expected_min_solids=int(d.get("expected_min_solids", d.get("min_solids", 1)) or 0),
            expected_min_faces=int(d.get("expected_min_faces", d.get("min_faces", 1)) or 0),
            expected_min_edges=int(d.get("expected_min_edges", d.get("min_edges", 0)) or 0),
            require_physical_groups=bool(d.get("require_physical_groups", True)),
            require_solver_region_map=bool(d.get("require_solver_region_map", True)),
            require_mesh_entity_map=bool(d.get("require_mesh_entity_map", True)),
            require_lineage=bool(d.get("require_lineage", False)),
            metadata=_meta(d.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class StepIfcBenchmarkRunSnapshot:
    """Single import/preprocessor run for a case."""

    ok: bool = False
    status: str = "not_run"
    import_report: dict[str, Any] = field(default_factory=dict)
    topology_summary: dict[str, Any] = field(default_factory=dict)
    cad_fem_summary: dict[str, Any] = field(default_factory=dict)
    persistent_names: list[dict[str, Any]] = field(default_factory=list)
    physical_group_ids: list[str] = field(default_factory=list)
    mesh_entity_map: dict[str, Any] = field(default_factory=dict)
    solver_region_map: dict[str, Any] = field(default_factory=dict)
    lineage_summary: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
            "ok": bool(self.ok),
            "status": self.status,
            "import_report": dict(self.import_report),
            "topology_summary": dict(self.topology_summary),
            "cad_fem_summary": dict(self.cad_fem_summary),
            "persistent_names": [dict(row) for row in self.persistent_names],
            "physical_group_ids": list(self.physical_group_ids),
            "mesh_entity_map": dict(self.mesh_entity_map),
            "solver_region_map": dict(self.solver_region_map),
            "lineage_summary": dict(self.lineage_summary),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StepIfcBenchmarkCaseResult:
    """Aggregated result for one STEP/IFC file."""

    case: StepIfcBenchmarkCaseSpec
    ok: bool = False
    status: str = "not_run"
    source_format: str = ""
    native_backend_used: bool = False
    native_brep_certified: bool = False
    repeat_stable: bool = False
    persistent_name_stable: bool = False
    physical_group_stable: bool = False
    solver_region_map_stable: bool = False
    mesh_entity_map_stable: bool = False
    lineage_verified: bool = False
    first_run: StepIfcBenchmarkRunSnapshot | None = None
    repeat_run: StepIfcBenchmarkRunSnapshot | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
            "case": self.case.to_dict(),
            "ok": bool(self.ok),
            "status": self.status,
            "source_format": self.source_format,
            "native_backend_used": bool(self.native_backend_used),
            "native_brep_certified": bool(self.native_brep_certified),
            "repeat_stable": bool(self.repeat_stable),
            "persistent_name_stable": bool(self.persistent_name_stable),
            "physical_group_stable": bool(self.physical_group_stable),
            "solver_region_map_stable": bool(self.solver_region_map_stable),
            "mesh_entity_map_stable": bool(self.mesh_entity_map_stable),
            "lineage_verified": bool(self.lineage_verified),
            "first_run": None if self.first_run is None else self.first_run.to_dict(),
            "repeat_run": None if self.repeat_run is None else self.repeat_run.to_dict(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class StepIfcNativeBenchmarkReport:
    """Full P8.5 STEP/IFC benchmark report."""

    ok: bool = False
    status: str = "not_run"
    case_count: int = 0
    passed_case_count: int = 0
    failed_case_count: int = 0
    blocked_case_count: int = 0
    capability: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cases: list[StepIfcBenchmarkCaseResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def contract(self) -> str:
        return STEP_IFC_NATIVE_BENCHMARK_CONTRACT

    def summary(self) -> dict[str, Any]:
        return {
            "case_count": int(self.case_count),
            "passed_case_count": int(self.passed_case_count),
            "failed_case_count": int(self.failed_case_count),
            "blocked_case_count": int(self.blocked_case_count),
            "native_case_count": sum(1 for case in self.cases if case.native_backend_used),
            "native_brep_certified_case_count": sum(1 for case in self.cases if case.native_brep_certified),
            "persistent_name_stable_count": sum(1 for case in self.cases if case.persistent_name_stable),
            "physical_group_stable_count": sum(1 for case in self.cases if case.physical_group_stable),
            "mesh_entity_map_stable_count": sum(1 for case in self.cases if case.mesh_entity_map_stable),
            "solver_region_map_stable_count": sum(1 for case in self.cases if case.solver_region_map_stable),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
            "ok": bool(self.ok),
            "status": self.status,
            "case_count": int(self.case_count),
            "passed_case_count": int(self.passed_case_count),
            "failed_case_count": int(self.failed_case_count),
            "blocked_case_count": int(self.blocked_case_count),
            "summary": self.summary(),
            "capability": dict(self.capability),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "cases": [case.to_dict() for case in self.cases],
            "metadata": dict(self.metadata),
        }


__all__ = [
    "STEP_IFC_NATIVE_BENCHMARK_CONTRACT",
    "StepIfcBenchmarkCaseSpec",
    "StepIfcBenchmarkRunSnapshot",
    "StepIfcBenchmarkCaseResult",
    "StepIfcNativeBenchmarkReport",
]
