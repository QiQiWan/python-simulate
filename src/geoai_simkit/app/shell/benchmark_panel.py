from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _candidate_paths(path: str | Path | None = None) -> list[Path]:
    if path is not None:
        return [Path(path)]
    cwd = Path.cwd()
    return [
        cwd / "reports" / "benchmark_gui_payload.json",
        cwd / "benchmark_reports" / "benchmark_gui_payload.json",
        cwd / "benchmark_gui_payload.json",
    ]


def load_benchmark_panel_payload(path: str | Path | None = None) -> dict[str, Any]:
    """Load the benchmark panel payload used by GUI shell compatibility tests."""

    source: Path | None = None
    payload: dict[str, Any] | None = None
    for candidate in _candidate_paths(path):
        payload = _read_json(candidate)
        if payload is not None:
            source = candidate
            break

    if payload is None:
        return {
            "available": False,
            "source": None,
            "accepted": None,
            "passed_count": 0,
            "benchmark_count": 0,
            "rows": [],
            "actions": [],
        }

    report_dir = Path(str(payload.get("report_dir") or source.parent if source else "."))
    markdown_path = payload.get("markdown_path")
    json_path = payload.get("json_path")
    if markdown_path is None and (report_dir / "benchmark_report.md").exists():
        markdown_path = str(report_dir / "benchmark_report.md")
    if json_path is None and (report_dir / "benchmark_report.json").exists():
        json_path = str(report_dir / "benchmark_report.json")

    actions: list[str] = []
    if markdown_path:
        actions.append("open_markdown")
    if json_path:
        actions.append("open_json")
    if report_dir:
        actions.append("open_report_dir")

    return {
        **payload,
        "available": True,
        "source": str(source) if source else None,
        "report_dir": str(report_dir),
        "markdown_path": None if markdown_path is None else str(markdown_path),
        "json_path": None if json_path is None else str(json_path),
        "actions": actions,
    }



STEP_IFC_GUI_READINESS_CONTRACT = "geoai_simkit_step_ifc_gui_readiness_panel_p90_v1"


def _normalize_report_path(path: str | Path | None = None) -> Path | None:
    candidates: list[Path]
    if path is not None:
        candidates = [Path(path)]
    else:
        cwd = Path.cwd()
        candidates = [
            cwd / "reports" / "step_ifc_native_benchmark.json",
            cwd / "reports" / "step_ifc_native_benchmark_dryrun.json",
            cwd / "step_ifc_native_benchmark.json",
        ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _fix_for_blocker(blocker: str) -> dict[str, str]:
    text = str(blocker or "")
    lower = text.lower()
    if "no native step/ifc runtime" in lower or "native import was required" in lower or "did not use a native backend" in lower:
        return {
            "action_id": "use_native_desktop_runtime",
            "title": "切换到 native STEP/IFC 桌面环境",
            "detail": "在 ifc conda 环境中运行 benchmark，确认 OCP / IfcOpenShell / Gmsh 均通过依赖自检；dry-run 结果不能作为 native 认证。",
            "command": "conda activate ifc && python tools/run_step_ifc_native_benchmark.py benchmarks/step_ifc/manifest.json --output reports/step_ifc_native_benchmark.json",
        }
    if "source file not found" in lower:
        return {
            "action_id": "add_missing_benchmark_file",
            "title": "补齐 benchmark 源文件",
            "detail": "检查 manifest 中的 source_path，放入真实 STEP/IFC 文件，或把相对路径改为相对 manifest 所在目录。",
            "command": "python tools/run_step_ifc_native_benchmark.py --write-template benchmarks/step_ifc/manifest.json",
        }
    if "solid topology count" in lower or "face topology count" in lower or "edge topology count" in lower:
        return {
            "action_id": "inspect_topology_extraction",
            "title": "检查 CAD 拓扑提取",
            "detail": "降低 expected_min_* 或修复 STEP/IFC native topology enumeration；优先确认 CadShapeStore 是否生成 solid/face/edge 记录。",
            "command": "python tools/run_step_ifc_native_benchmark.py benchmarks/step_ifc/manifest.json --allow-fallback --output reports/step_ifc_native_benchmark_dryrun.json",
        }
    if "persistent-name duplicates" in lower or "persistent topology naming" in lower:
        return {
            "action_id": "stabilize_persistent_naming",
            "title": "稳定 persistent naming",
            "detail": "补充 face/edge bounds、orientation、source GUID、OCC subshape hash；复杂曲面文件应加入重复导入 benchmark。",
            "command": "python tools/run_persistent_naming_benchmark.py benchmarks/step_ifc --output reports/persistent_naming_benchmark.json",
        }
    if "physical group" in lower:
        return {
            "action_id": "rebuild_physical_groups",
            "title": "重建 CAD-FEM physical groups",
            "detail": "先构建 topology identity index，再运行 CAD-FEM preprocessor，确保 solid 转 volume、face 转 surface。",
            "command": "python tools/run_step_ifc_native_benchmark.py benchmarks/step_ifc/manifest.json --allow-fallback --output reports/step_ifc_native_benchmark_dryrun.json",
        }
    if "mesh entity map" in lower:
        return {
            "action_id": "refresh_mesh_entity_map",
            "title": "刷新网格实体映射",
            "detail": "确认 physical groups 已生成，再将 planned_physical_groups 写入 mesh entity map，供 Gmsh/meshio 后续标记使用。",
            "command": "python tools/run_step_ifc_native_benchmark.py benchmarks/step_ifc/manifest.json --allow-fallback --output reports/step_ifc_native_benchmark_dryrun.json",
        }
    if "solver region map" in lower or "material" in lower:
        return {
            "action_id": "assign_volume_materials",
            "title": "补齐体材料与求解区域",
            "detail": "给每个 volume physical group 绑定 material_id；没有材料的 volume 不能进入求解前检查。",
            "command": "在 GUI 中选中 solid/volume → 语义/材料/阶段 → 赋 Face/Edge/Solid 材料/阶段",
        }
    if "occ boolean history" in lower or "lineage" in lower or "native history map" in lower:
        return {
            "action_id": "run_native_boolean_lineage_case",
            "title": "运行 native OCC 布尔历史 benchmark",
            "detail": "require_lineage=true 的 case 必须来自真实 OCC 布尔操作，并包含 split/merge/generated/deleted history map 证据。",
            "command": "python tools/run_step_ifc_native_benchmark.py benchmarks/step_ifc/manifest.json --output reports/step_ifc_native_benchmark.json",
        }
    return {
        "action_id": "inspect_case_artifacts",
        "title": "查看 case artifacts",
        "detail": "打开该 case 的 cad_fem_preprocessor、planned_mesh_entity_map、solver_region_map 和 lineage_summary，定位失败环节。",
        "command": "查看 reports/step_ifc_native_benchmark_artifacts",
    }


def _case_id(case: dict[str, Any]) -> str:
    spec = dict(case.get("case", {}) or {})
    return str(spec.get("case_id") or spec.get("source_path") or "case")


def _case_artifact_dir(case: dict[str, Any]) -> str:
    first = dict(case.get("first_run", {}) or {})
    meta = dict(first.get("metadata", {}) or {})
    cad_path = meta.get("cad_fem_payload_path")
    if cad_path:
        try:
            return str(Path(str(cad_path)).parent)
        except Exception:
            return ""
    return ""


def _build_case_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in list(report.get("cases", []) or []):
        if not isinstance(case, dict):
            continue
        first = dict(case.get("first_run", {}) or {})
        topo = dict(first.get("topology_summary", {}) or {})
        rows.append(
            {
                "case_id": _case_id(case),
                "status": str(case.get("status") or "unknown"),
                "ok": bool(case.get("ok")),
                "native_backend_used": bool(case.get("native_backend_used")),
                "native_brep_certified": bool(case.get("native_brep_certified")),
                "persistent_name_stable": bool(case.get("persistent_name_stable")),
                "physical_group_stable": bool(case.get("physical_group_stable")),
                "mesh_entity_map_stable": bool(case.get("mesh_entity_map_stable")),
                "solver_region_map_stable": bool(case.get("solver_region_map_stable")),
                "lineage_verified": bool(case.get("lineage_verified")),
                "solid_count": int(topo.get("solid_count", 0) or 0),
                "face_count": int(topo.get("face_count", 0) or 0),
                "edge_count": int(topo.get("edge_count", 0) or 0),
                "blockers": [str(item) for item in list(case.get("blockers", []) or [])],
                "warnings": [str(item) for item in list(case.get("warnings", []) or [])],
                "artifact_dir": _case_artifact_dir(case),
            }
        )
    return rows


def _build_fix_suggestions(report: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for blocker in [str(item) for item in list(report.get("blockers", []) or [])]:
        fix = _fix_for_blocker(blocker)
        key = ("report", blocker)
        if key not in seen:
            seen.add(key)
            suggestions.append({"case_id": "report", "blocker": blocker, **fix})
    for case in list(report.get("cases", []) or []):
        if not isinstance(case, dict):
            continue
        cid = _case_id(case)
        for blocker in [str(item) for item in list(case.get("blockers", []) or [])]:
            fix = _fix_for_blocker(blocker)
            key = (cid, blocker)
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({"case_id": cid, "blocker": blocker, "artifact_dir": _case_artifact_dir(case), **fix})
    return suggestions


def load_step_ifc_benchmark_readiness_payload(path: str | Path | None = None) -> dict[str, Any]:
    """Load a P8.5 report and convert blockers into GUI-ready fix actions."""

    source = _normalize_report_path(path)
    if source is None:
        return {
            "contract": STEP_IFC_GUI_READINESS_CONTRACT,
            "available": False,
            "source": None,
            "status": "missing_report",
            "summary": {},
            "case_rows": [],
            "fix_suggestions": [],
            "actions": ["run_native_benchmark", "run_fallback_dryrun", "write_manifest_template"],
            "message": "No STEP/IFC benchmark report was found under reports/.",
        }
    report = _read_json(source) or {}
    summary = dict(report.get("summary", {}) or {})
    case_rows = _build_case_rows(report)
    suggestions = _build_fix_suggestions(report)
    artifacts_dir = str(dict(report.get("metadata", {}) or {}).get("artifacts_dir") or source.parent)
    actions = ["refresh_report", "open_report_json", "open_artifacts_dir", "run_native_benchmark", "run_fallback_dryrun"]
    if suggestions:
        actions.append("apply_fix_suggestion")
    return {
        "contract": STEP_IFC_GUI_READINESS_CONTRACT,
        "available": True,
        "source": str(source),
        "status": str(report.get("status") or "unknown"),
        "ok": bool(report.get("ok")),
        "summary": summary,
        "case_count": int(report.get("case_count", summary.get("case_count", len(case_rows))) or 0),
        "passed_case_count": int(report.get("passed_case_count", summary.get("passed_case_count", 0)) or 0),
        "failed_case_count": int(report.get("failed_case_count", 0) or 0),
        "blocked_case_count": int(report.get("blocked_case_count", 0) or 0),
        "case_rows": case_rows,
        "fix_suggestions": suggestions,
        "blockers": [str(item) for item in list(report.get("blockers", []) or [])],
        "warnings": [str(item) for item in list(report.get("warnings", []) or [])],
        "artifacts_dir": artifacts_dir,
        "actions": actions,
        "native_certification": bool(summary.get("native_brep_certified_case_count", 0)),
    }


__all__ = ["load_benchmark_panel_payload", "load_step_ifc_benchmark_readiness_payload", "STEP_IFC_GUI_READINESS_CONTRACT"]
