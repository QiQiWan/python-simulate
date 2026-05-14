from __future__ import annotations

"""P8.5 real STEP/IFC benchmark and certification runner.

The runner is evidence-driven.  With ``require_native=True`` it does not convert
surrogate imports into certification claims; cases are blocked unless the host
has a matching native STEP/IFC runtime.  With ``require_native=False`` the same
pipeline performs a dry-run on explicit benchmark fixtures so topology identity,
CAD-FEM physical groups, solver region maps and mesh entity maps can be tested
in CI.
"""

from hashlib import sha1
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from geoai_simkit.core.cad_fem_preprocessor import CadFemReadinessReport
from geoai_simkit.core.step_ifc_native_benchmark import (
    STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
    StepIfcBenchmarkCaseResult,
    StepIfcBenchmarkCaseSpec,
    StepIfcBenchmarkRunSnapshot,
    StepIfcNativeBenchmarkReport,
)
from geoai_simkit.geometry.persistent_naming import PersistentTopologyNamer
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap
from geoai_simkit.services.cad_fem_preprocessor import build_cad_fem_preprocessor
from geoai_simkit.services.demo_project_runner import load_demo_project
from geoai_simkit.services.step_ifc_shape_import import import_step_ifc_solid_topology, probe_step_ifc_import_capability
from geoai_simkit.services.topology_identity_service import build_topology_identity_index

_STEP_IFC_SUFFIXES = {".step", ".stp", ".ifc"}


def _safe_id(text: str, fallback: str = "case") -> str:
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(text or ""))
    clean = "_".join(part for part in clean.split("_") if part)
    return clean or fallback


def _case_files(input_path: str | Path) -> list[Path]:
    root = Path(input_path)
    if root.is_file() and root.suffix.lower() in _STEP_IFC_SUFFIXES:
        return [root]
    if not root.exists() or not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in _STEP_IFC_SUFFIXES)


def _manifest_cases(path: Path) -> list[StepIfcBenchmarkCaseSpec]:
    if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
        return []
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = list(data.get("cases", data if isinstance(data, list) else []) or [])
    base = path.parent
    cases: list[StepIfcBenchmarkCaseSpec] = []
    for row in rows:
        spec = StepIfcBenchmarkCaseSpec.from_dict(row)
        source = Path(spec.source_path)
        if spec.source_path and not source.is_absolute():
            spec = StepIfcBenchmarkCaseSpec(
                source_path=str((base / source).resolve()),
                case_id=spec.case_id,
                category=spec.category,
                require_native=spec.require_native,
                expected_min_solids=spec.expected_min_solids,
                expected_min_faces=spec.expected_min_faces,
                expected_min_edges=spec.expected_min_edges,
                require_physical_groups=spec.require_physical_groups,
                require_solver_region_map=spec.require_solver_region_map,
                require_mesh_entity_map=spec.require_mesh_entity_map,
                require_lineage=spec.require_lineage,
                metadata=dict(spec.metadata),
            )
        cases.append(spec)
    return cases


def discover_step_ifc_benchmark_cases(input_path: str | Path, *, require_native: bool | None = None) -> list[StepIfcBenchmarkCaseSpec]:
    """Discover benchmark cases from a directory, single file or JSON manifest."""

    root = Path(input_path)
    manifest = _manifest_cases(root)
    if manifest:
        return [
            StepIfcBenchmarkCaseSpec(
                source_path=case.source_path,
                case_id=case.case_id or _safe_id(Path(case.source_path).stem),
                category=case.category,
                require_native=require_native if case.require_native is None else case.require_native,
                expected_min_solids=case.expected_min_solids,
                expected_min_faces=case.expected_min_faces,
                expected_min_edges=case.expected_min_edges,
                require_physical_groups=case.require_physical_groups,
                require_solver_region_map=case.require_solver_region_map,
                require_mesh_entity_map=case.require_mesh_entity_map,
                require_lineage=case.require_lineage,
                metadata=dict(case.metadata),
            )
            for case in manifest
        ]
    return [
        StepIfcBenchmarkCaseSpec(
            source_path=str(path),
            case_id=_safe_id(path.stem),
            category="real_step_ifc_file",
            require_native=require_native,
        )
        for path in _case_files(root)
    ]


def _names_for_topology_records(records: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    namer = PersistentTopologyNamer()
    names: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    duplicate_count = 0
    for row in records:
        item = namer.name_entity(dict(row), fallback_kind=str(row.get("kind") or "entity"))
        pid = str(item.get("persistent_id") or "")
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > 1:
            duplicate_count += 1
            item["duplicate_resolved"] = True
            item["persistent_id"] = f"{pid}:dup_{seen[pid]}"
        names.append(item)
    names.sort(key=lambda x: (str(x.get("kind") or ""), str(x.get("entity_id") or ""), str(x.get("persistent_id") or "")))
    return names, duplicate_count


def _physical_group_signature(report: CadFemReadinessReport) -> list[str]:
    rows = []
    for group in report.physical_groups:
        rows.append("|".join([str(group.dimension), group.role, group.material_id, ",".join(sorted(group.topology_keys))]))
    return sorted(rows)


def _persistent_signature(names: list[dict[str, Any]]) -> list[str]:
    return sorted(f"{row.get('kind')}|{row.get('semantic_role')}|{row.get('stable_key')}|{row.get('fingerprint')}" for row in names)


def _mesh_entity_signature(mesh_map: Mapping[str, Any]) -> list[str]:
    return sorted(str(item) for item in list(mesh_map.get("metadata", {}).get("planned_physical_groups", []) or []))


def _solver_region_signature(region_map: Mapping[str, Any]) -> list[str]:
    return sorted(f"{row.get('physical_group_id')}|{row.get('material_id')}|{row.get('source_entity_ids')}" for row in list(region_map.get("regions", []) or []))


def _build_planned_mesh_entity_map(cad_report: CadFemReadinessReport) -> dict[str, Any]:
    """Build a pre-mesh entity map that can be carried into Gmsh/meshio."""

    mesh_map = MeshEntityMap(metadata={"contract": "geoai_simkit_pre_mesh_entity_map_p85_v1", "planned_physical_groups": []})
    for group in cad_report.physical_groups:
        row = group.to_dict()
        mesh_map.metadata["planned_physical_groups"].append(row)
        if group.dimension == 3:
            mesh_map.block_to_cells[group.id] = []
        elif group.dimension == 2:
            mesh_map.face_to_faces[group.id] = []
        elif group.dimension == 1:
            mesh_map.interface_to_faces[group.id] = []
    return mesh_map.to_dict()


def _build_solver_region_map(cad_report: CadFemReadinessReport) -> dict[str, Any]:
    volume_groups = [group for group in cad_report.physical_groups if group.dimension == 3]
    surface_groups = [group for group in cad_report.physical_groups if group.dimension == 2]
    regions = []
    missing_material: list[str] = []
    for group in volume_groups:
        if not group.material_id:
            missing_material.append(group.id)
        regions.append(
            {
                "physical_group_id": group.id,
                "dimension": group.dimension,
                "material_id": group.material_id,
                "phase_ids": list(group.phase_ids),
                "topology_keys": list(group.topology_keys),
                "source_entity_ids": list(group.source_entity_ids),
                "role": group.role or "volume_region",
            }
        )
    return {
        "contract": "geoai_simkit_solver_region_map_p85_v1",
        "ok": not missing_material and bool(regions),
        "region_count": len(regions),
        "surface_group_count": len(surface_groups),
        "regions": regions,
        "missing_material_physical_groups": missing_material,
        "boundary_candidate_count": len(cad_report.boundary_candidates),
        "solver_requirements": dict(cad_report.solver_requirements),
    }


def _lineage_summary(project: Any) -> dict[str, Any]:
    store = getattr(project, "cad_shape_store", None)
    rows = list(getattr(store, "topology_lineage", {}).values()) if store is not None else []
    native_rows = [row for row in rows if getattr(row, "native_backend_used", False) or getattr(row, "confidence", "") == "native"]
    types: dict[str, int] = {}
    for row in rows:
        lineage_type = str(getattr(row, "lineage_type", "unknown") or "unknown")
        types[lineage_type] = types.get(lineage_type, 0) + 1
    return {
        "contract": "geoai_simkit_boolean_lineage_benchmark_p85_v1",
        "lineage_count": len(rows),
        "native_lineage_count": len(native_rows),
        "lineage_types": types,
        "operation_count": len(getattr(store, "operation_history", {}) or {}) if store is not None else 0,
        "native_history_map_available": bool(native_rows),
        "note": "Import-only cases may have operation history without split/merge lineage; set require_lineage=true in the manifest for boolean history certification cases.",
    }


def _validate_run_snapshot(
    spec: StepIfcBenchmarkCaseSpec,
    *,
    import_report: Mapping[str, Any],
    topology_summary: Mapping[str, Any],
    cad_report: CadFemReadinessReport,
    duplicate_name_count: int,
    mesh_entity_map: Mapping[str, Any],
    solver_region_map: Mapping[str, Any],
    lineage_summary: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not bool(import_report.get("ok")):
        blockers.append(f"Import failed: {import_report.get('status')}.")
    if spec.require_native and not bool(import_report.get("native_backend_used")):
        blockers.append("Native import was required but this run did not use a native backend.")
    if int(topology_summary.get("solid_count", 0) or 0) < spec.expected_min_solids:
        blockers.append(f"Solid topology count below expectation: {topology_summary.get('solid_count', 0)} < {spec.expected_min_solids}.")
    if int(topology_summary.get("face_count", 0) or 0) < spec.expected_min_faces:
        blockers.append(f"Face topology count below expectation: {topology_summary.get('face_count', 0)} < {spec.expected_min_faces}.")
    if int(topology_summary.get("edge_count", 0) or 0) < spec.expected_min_edges:
        blockers.append(f"Edge topology count below expectation: {topology_summary.get('edge_count', 0)} < {spec.expected_min_edges}.")
    if duplicate_name_count:
        blockers.append(f"Persistent-name duplicates detected: {duplicate_name_count}.")
    if spec.require_physical_groups and not cad_report.physical_groups:
        blockers.append("No CAD-FEM physical groups were generated.")
    if spec.require_mesh_entity_map and not list(mesh_entity_map.get("metadata", {}).get("planned_physical_groups", []) or []):
        blockers.append("No planned mesh entity map entries were generated.")
    if spec.require_solver_region_map and not bool(solver_region_map.get("ok")):
        blockers.append("Solver region map is incomplete or lacks material-bearing volume groups.")
    if spec.require_lineage and not bool(lineage_summary.get("native_history_map_available")):
        blockers.append("Native OCC boolean history map was required but no native split/merge lineage was present.")
    warnings.extend(str(item) for item in list(import_report.get("warnings", []) or []))
    warnings.extend(str(item) for item in cad_report.warnings)
    if not bool(import_report.get("native_brep_certified")):
        warnings.append("Native BRep certification is false for this case; exact OCC TopoDS serialization/enumeration was not proven in this run.")
    return blockers, warnings


def _run_case_once(
    spec: StepIfcBenchmarkCaseSpec,
    *,
    require_native: bool,
    output_root: Path,
    run_label: str,
    default_element_size: float | None,
) -> StepIfcBenchmarkRunSnapshot:
    project = load_demo_project("foundation_pit_3d_beta")
    source = Path(spec.source_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not source.exists():
        return StepIfcBenchmarkRunSnapshot(
            ok=False,
            status="source_not_found",
            blockers=[f"Source file not found: {source}."],
            metadata={"case_id": spec.case_id, "source_path": str(source)},
        )
    run_root = output_root / _safe_id(spec.case_id or source.stem) / run_label
    import_report = import_step_ifc_solid_topology(
        project,
        source,
        output_dir=run_root / "import_refs",
        require_native=require_native,
        attach=True,
        export_references=True,
    )
    import_payload = import_report.to_dict()
    index = build_topology_identity_index(project, attach=True)
    topology_summary = index.summary()
    cad_report = build_cad_fem_preprocessor(project, attach=True, default_element_size=default_element_size)
    records = [topo.to_dict() for topo in getattr(project.cad_shape_store, "topology_records", {}).values()]
    names, duplicate_count = _names_for_topology_records(records)
    mesh_entity_map = _build_planned_mesh_entity_map(cad_report)
    solver_region_map = _build_solver_region_map(cad_report)
    lineage = _lineage_summary(project)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "cad_fem_preprocessor.json").write_text(json.dumps(cad_report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "planned_mesh_entity_map.json").write_text(json.dumps(mesh_entity_map, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "solver_region_map.json").write_text(json.dumps(solver_region_map, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "lineage_summary.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")
    run_blockers, run_warnings = _validate_run_snapshot(
        spec,
        import_report=import_payload,
        topology_summary=topology_summary,
        cad_report=cad_report,
        duplicate_name_count=duplicate_count,
        mesh_entity_map=mesh_entity_map,
        solver_region_map=solver_region_map,
        lineage_summary=lineage,
    )
    blockers.extend(run_blockers)
    warnings.extend(run_warnings)
    digest = sha1(source.read_bytes()).hexdigest()[:20]
    status = "passed" if not blockers else "blocked" if import_report.status in {"native_import_unavailable", "source_not_found"} else "failed"
    return StepIfcBenchmarkRunSnapshot(
        ok=not blockers,
        status=status,
        import_report=import_payload,
        topology_summary=topology_summary,
        cad_fem_summary=cad_report.summary(),
        persistent_names=names[:200],
        physical_group_ids=sorted(group.id for group in cad_report.physical_groups),
        mesh_entity_map=mesh_entity_map,
        solver_region_map=solver_region_map,
        lineage_summary=lineage,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "source_digest": digest,
            "case_id": spec.case_id,
            "run_label": run_label,
            "duplicate_name_count": duplicate_count,
            "persistent_signature": _persistent_signature(names),
            "physical_group_signature": _physical_group_signature(cad_report),
            "mesh_entity_signature": _mesh_entity_signature(mesh_entity_map),
            "solver_region_signature": _solver_region_signature(solver_region_map),
            "cad_fem_payload_path": str(run_root / "cad_fem_preprocessor.json"),
        },
    )


def _compare_snapshots(first: StepIfcBenchmarkRunSnapshot, second: StepIfcBenchmarkRunSnapshot) -> dict[str, Any]:
    first_meta = first.metadata
    second_meta = second.metadata
    persistent_stable = list(first_meta.get("persistent_signature", []) or []) == list(second_meta.get("persistent_signature", []) or [])
    pg_stable = list(first_meta.get("physical_group_signature", []) or []) == list(second_meta.get("physical_group_signature", []) or [])
    mesh_stable = list(first_meta.get("mesh_entity_signature", []) or []) == list(second_meta.get("mesh_entity_signature", []) or [])
    solver_stable = list(first_meta.get("solver_region_signature", []) or []) == list(second_meta.get("solver_region_signature", []) or [])
    topo_stable = {
        key: first.topology_summary.get(key) == second.topology_summary.get(key)
        for key in ("solid_count", "face_count", "edge_count", "topology_count")
    }
    return {
        "persistent_name_stable": persistent_stable,
        "physical_group_stable": pg_stable,
        "mesh_entity_map_stable": mesh_stable,
        "solver_region_map_stable": solver_stable,
        "topology_count_stable": all(topo_stable.values()),
        "topology_count_comparison": topo_stable,
    }


def _case_result(
    spec: StepIfcBenchmarkCaseSpec,
    *,
    output_root: Path,
    default_require_native: bool,
    repeat_count: int,
    default_element_size: float | None,
) -> StepIfcBenchmarkCaseResult:
    require_native = default_require_native if spec.require_native is None else bool(spec.require_native)
    first = _run_case_once(spec, require_native=require_native, output_root=output_root, run_label="run_1", default_element_size=default_element_size)
    repeat = None
    comparison = {
        "persistent_name_stable": False,
        "physical_group_stable": False,
        "mesh_entity_map_stable": False,
        "solver_region_map_stable": False,
        "topology_count_stable": False,
    }
    blockers = list(first.blockers)
    warnings = list(first.warnings)
    if repeat_count >= 2 and first.ok:
        repeat = _run_case_once(spec, require_native=require_native, output_root=output_root, run_label="run_2", default_element_size=default_element_size)
        comparison = _compare_snapshots(first, repeat)
        blockers.extend(repeat.blockers)
        warnings.extend(repeat.warnings)
        if not comparison["persistent_name_stable"]:
            blockers.append("Persistent topology naming signature changed between repeated imports.")
        if spec.require_physical_groups and not comparison["physical_group_stable"]:
            blockers.append("Physical group signature changed between repeated imports.")
        if spec.require_mesh_entity_map and not comparison["mesh_entity_map_stable"]:
            blockers.append("Planned mesh entity map signature changed between repeated imports.")
        if spec.require_solver_region_map and not comparison["solver_region_map_stable"]:
            blockers.append("Solver region map signature changed between repeated imports.")
    elif repeat_count >= 2 and not first.ok:
        warnings.append("Repeat stability was skipped because the first run did not pass.")
    else:
        comparison = {
            "persistent_name_stable": True,
            "physical_group_stable": True,
            "mesh_entity_map_stable": True,
            "solver_region_map_stable": True,
            "topology_count_stable": True,
            "note": "repeat_count < 2; stability inferred from single run only",
        }
    lineage_verified = bool(first.lineage_summary.get("native_history_map_available")) or not spec.require_lineage
    if spec.require_lineage and not lineage_verified:
        blockers.append("Lineage verification failed: require_lineage=true but native history map was unavailable.")
    status = "passed" if not blockers and first.ok and (repeat is None or repeat.ok) else "blocked" if first.status == "blocked" else "failed"
    import_payload = first.import_report
    return StepIfcBenchmarkCaseResult(
        case=spec,
        ok=status == "passed",
        status=status,
        source_format=str(import_payload.get("source_format") or Path(spec.source_path).suffix.lower().lstrip(".")),
        native_backend_used=bool(import_payload.get("native_backend_used")),
        native_brep_certified=bool(import_payload.get("native_brep_certified")),
        repeat_stable=all(bool(comparison.get(key)) for key in ("persistent_name_stable", "physical_group_stable", "mesh_entity_map_stable", "solver_region_map_stable")),
        persistent_name_stable=bool(comparison.get("persistent_name_stable")),
        physical_group_stable=bool(comparison.get("physical_group_stable")),
        solver_region_map_stable=bool(comparison.get("solver_region_map_stable")),
        mesh_entity_map_stable=bool(comparison.get("mesh_entity_map_stable")),
        lineage_verified=lineage_verified,
        first_run=first,
        repeat_run=repeat,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        evidence={"repeat_comparison": comparison, "require_native": require_native, "repeat_count": repeat_count},
    )


def run_step_ifc_native_benchmark(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    require_native: bool = True,
    repeat_count: int = 2,
    default_element_size: float | None = 1.0,
) -> StepIfcNativeBenchmarkReport:
    """Run the full P8.5 benchmark suite on STEP/IFC files or a manifest."""

    capability = probe_step_ifc_import_capability().to_dict()
    cases = discover_step_ifc_benchmark_cases(input_path, require_native=require_native)
    output_root = Path(output_path).parent / "step_ifc_native_benchmark_artifacts" if output_path is not None else Path("reports/step_ifc_native_benchmark_artifacts")
    blockers: list[str] = []
    warnings: list[str] = []
    if not cases:
        blockers.append(f"No STEP/IFC benchmark cases found under {Path(input_path)}.")
    if require_native and not bool(capability.get("native_step_possible") or capability.get("native_ifc_possible")):
        blockers.append("No native STEP/IFC runtime is available on this host; run in the desktop OCP/IfcOpenShell/Gmsh environment or pass --allow-fallback for a dry-run.")
    results: list[StepIfcBenchmarkCaseResult] = []
    if not blockers:
        output_root.mkdir(parents=True, exist_ok=True)
        for spec in cases:
            results.append(
                _case_result(
                    spec,
                    output_root=output_root,
                    default_require_native=require_native,
                    repeat_count=repeat_count,
                    default_element_size=default_element_size,
                )
            )
    passed = sum(1 for case in results if case.ok)
    failed = sum(1 for case in results if not case.ok and case.status != "blocked")
    blocked = sum(1 for case in results if case.status == "blocked") + (1 if blockers else 0)
    status = "blocked" if blockers else "passed" if results and passed == len(results) else "failed"
    report = StepIfcNativeBenchmarkReport(
        ok=not blockers and bool(results) and passed == len(results),
        status=status,
        case_count=len(results),
        passed_case_count=passed,
        failed_case_count=failed,
        blocked_case_count=blocked,
        capability=capability,
        blockers=blockers,
        warnings=warnings,
        cases=results,
        metadata={
            "input_path": str(input_path),
            "require_native": bool(require_native),
            "repeat_count": int(repeat_count),
            "default_element_size": default_element_size,
            "artifacts_dir": str(output_root),
        },
    )
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def write_step_ifc_benchmark_manifest_template(path: str | Path) -> Path:
    """Write a manifest template that users can fill with real STEP/IFC files."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract": STEP_IFC_NATIVE_BENCHMARK_CONTRACT,
        "cases": [
            {
                "case_id": "simple_wall_ifc",
                "source_path": "benchmarks/step_ifc/simple_wall.ifc",
                "category": "simple_ifc_product",
                "require_native": True,
                "expected_min_solids": 1,
                "expected_min_faces": 6,
                "expected_min_edges": 12,
                "require_physical_groups": True,
                "require_solver_region_map": True,
                "require_mesh_entity_map": True,
                "require_lineage": False,
            },
            {
                "case_id": "complex_surface_step_boolean_history",
                "source_path": "benchmarks/step_ifc/complex_surface_boolean.step",
                "category": "complex_step_surface_boolean_history",
                "require_native": True,
                "expected_min_solids": 1,
                "expected_min_faces": 8,
                "expected_min_edges": 12,
                "require_lineage": True,
                "metadata": {"purpose": "persistent naming plus OCC native split/merge history map"},
            },
        ],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


__all__ = [
    "discover_step_ifc_benchmark_cases",
    "run_step_ifc_native_benchmark",
    "write_step_ifc_benchmark_manifest_template",
]
