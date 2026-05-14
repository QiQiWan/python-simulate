from __future__ import annotations

"""Benchmark harness for persistent topology naming on real STEP/IFC cases.

The harness is intentionally file-driven.  It does not ship synthetic success
claims for complex curved STEP files; it reports missing files or missing native
runtimes as blockers so desktop certification remains explicit.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from geoai_simkit.geometry.persistent_naming import PersistentTopologyNamer
from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology, probe_step_ifc_import_capability

PERSISTENT_NAMING_BENCHMARK_CONTRACT = "geoai_simkit_persistent_naming_real_file_benchmark_v1"


@dataclass(slots=True)
class PersistentNamingBenchmarkCase:
    source_path: str
    ok: bool = False
    status: str = "not_run"
    source_format: str = ""
    native_backend_used: bool = False
    native_brep_certified: bool = False
    topology_record_count: int = 0
    persistent_name_count: int = 0
    duplicate_name_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "ok": bool(self.ok),
            "status": self.status,
            "source_format": self.source_format,
            "native_backend_used": bool(self.native_backend_used),
            "native_brep_certified": bool(self.native_brep_certified),
            "topology_record_count": int(self.topology_record_count),
            "persistent_name_count": int(self.persistent_name_count),
            "duplicate_name_count": int(self.duplicate_name_count),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PersistentNamingBenchmarkReport:
    contract: str = PERSISTENT_NAMING_BENCHMARK_CONTRACT
    ok: bool = False
    status: str = "not_run"
    case_count: int = 0
    passed_case_count: int = 0
    failed_case_count: int = 0
    duplicate_name_count: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cases: list[PersistentNamingBenchmarkCase] = field(default_factory=list)
    capability: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "ok": bool(self.ok),
            "status": self.status,
            "case_count": int(self.case_count),
            "passed_case_count": int(self.passed_case_count),
            "failed_case_count": int(self.failed_case_count),
            "duplicate_name_count": int(self.duplicate_name_count),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "cases": [case.to_dict() for case in self.cases],
            "capability": dict(self.capability),
            "metadata": dict(self.metadata),
        }


def _case_files(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    if root.is_file():
        return [root]
    suffixes = {".step", ".stp", ".ifc"}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def _names_for_topology_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    namer = PersistentTopologyNamer()
    names: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for row in records:
        item = namer.name_entity(row, fallback_kind=str(row.get("kind") or "entity"))
        pid = str(item.get("persistent_id") or "")
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > 1:
            item["duplicate_resolved"] = True
            item["persistent_id"] = f"{pid}:dup_{seen[pid]}"
        names.append(item)
    return names, sum(max(0, count - 1) for count in seen.values())


def run_persistent_naming_benchmark(
    input_dir: str | Path,
    *,
    output_path: str | Path | None = None,
    require_native: bool = True,
) -> PersistentNamingBenchmarkReport:
    capability = probe_step_ifc_import_capability().to_dict()
    files = _case_files(input_dir)
    blockers: list[str] = []
    warnings: list[str] = []
    if not files:
        blockers.append(f"No STEP/IFC benchmark files found under {Path(input_dir)}.")
    if require_native and not bool(capability.get("native_step_possible") or capability.get("native_ifc_possible")):
        blockers.append("Native STEP/IFC runtime is unavailable; cannot certify complex surface persistent naming.")
    cases: list[PersistentNamingBenchmarkCase] = []
    if not blockers:
        from geoai_simkit.services.demo_project_runner import load_demo_project

        for path in files:
            case = PersistentNamingBenchmarkCase(source_path=str(path), source_format=path.suffix.lower().lstrip("."))
            try:
                project = load_demo_project("foundation_pit_3d_beta")
                report = import_step_ifc_solid_topology(project, path, require_native=require_native, attach=True, export_references=False)
                records = [topo.to_dict() for topo in project.cad_shape_store.topology_records.values()]
                names, duplicate_count = _names_for_topology_records(records)
                case.ok = bool(report.ok) and bool(names) and duplicate_count == 0
                case.status = "passed" if case.ok else "failed"
                case.native_backend_used = bool(report.native_backend_used)
                case.native_brep_certified = bool(report.native_brep_certified)
                case.topology_record_count = len(records)
                case.persistent_name_count = len(names)
                case.duplicate_name_count = duplicate_count
                case.warnings = list(report.warnings)
                if duplicate_count:
                    case.warnings.append(f"Persistent-name duplicates detected: {duplicate_count}.")
                case.metadata = {"import_report": report.to_dict(), "persistent_names": names[:50]}
            except Exception as exc:
                case.ok = False
                case.status = "exception"
                case.blockers = [f"{type(exc).__name__}: {exc}"]
            cases.append(case)
    passed = sum(1 for case in cases if case.ok)
    failed = sum(1 for case in cases if not case.ok)
    duplicate_count = sum(case.duplicate_name_count for case in cases)
    status = "blocked" if blockers else ("passed" if cases and failed == 0 else "failed")
    result = PersistentNamingBenchmarkReport(
        ok=not blockers and bool(cases) and failed == 0,
        status=status,
        case_count=len(cases),
        passed_case_count=passed,
        failed_case_count=failed,
        duplicate_name_count=duplicate_count,
        blockers=blockers,
        warnings=warnings,
        cases=cases,
        capability=capability,
        metadata={"require_native": bool(require_native), "input_dir": str(input_dir)},
    )
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = [
    "PersistentNamingBenchmarkCase",
    "PersistentNamingBenchmarkReport",
    "run_persistent_naming_benchmark",
]
