from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.benchmark_panel import (
    STEP_IFC_GUI_READINESS_CONTRACT,
    load_step_ifc_benchmark_readiness_payload,
)
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def _write_report(path: Path) -> Path:
    payload = {
        "contract": "geoai_simkit_step_ifc_native_benchmark_p85_v1",
        "ok": False,
        "status": "failed",
        "case_count": 2,
        "passed_case_count": 1,
        "failed_case_count": 1,
        "blocked_case_count": 0,
        "summary": {
            "case_count": 2,
            "passed_case_count": 1,
            "native_brep_certified_case_count": 0,
        },
        "metadata": {"artifacts_dir": str(path.parent / "artifacts")},
        "cases": [
            {
                "case": {"case_id": "wall_ifc", "source_path": "wall.ifc"},
                "ok": True,
                "status": "passed",
                "native_backend_used": True,
                "native_brep_certified": True,
                "persistent_name_stable": True,
                "physical_group_stable": True,
                "mesh_entity_map_stable": True,
                "solver_region_map_stable": True,
                "lineage_verified": True,
                "first_run": {"topology_summary": {"solid_count": 1, "face_count": 6, "edge_count": 12}, "metadata": {}},
            },
            {
                "case": {"case_id": "bad_step", "source_path": "bad.step"},
                "ok": False,
                "status": "failed",
                "native_backend_used": False,
                "native_brep_certified": False,
                "persistent_name_stable": False,
                "physical_group_stable": False,
                "mesh_entity_map_stable": False,
                "solver_region_map_stable": False,
                "lineage_verified": False,
                "blockers": [
                    "Native import was required but this run did not use a native backend.",
                    "Solver region map is incomplete or lacks material-bearing volume groups.",
                ],
                "first_run": {
                    "topology_summary": {"solid_count": 1, "face_count": 6, "edge_count": 12},
                    "metadata": {"cad_fem_payload_path": str(path.parent / "artifacts" / "bad_step" / "run_1" / "cad_fem_preprocessor.json")},
                },
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_iter150_version_and_payload_expose_gui_cleanup_contract() -> None:
    assert __version__ == "1.5.4-viewport-workplane-hover-creation"
    payload = build_phase_workbench_qt_payload()
    assert payload["benchmark_readiness_panel"]["contract"] == STEP_IFC_GUI_READINESS_CONTRACT
    assert payload["benchmark_readiness_panel"]["clickable_fix_suggestions"] is True
    cleanup = payload["gui_cleanup"]
    assert cleanup["right_dock_tabs"] == ["属性", "语义/材料/阶段", "材料库"]
    assert "Benchmark" in cleanup["bottom_tabs"]
    assert cleanup["floating_help_dock"] is True


def test_iter150_step_ifc_report_loads_case_rows_and_clickable_fixes(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "reports" / "step_ifc_native_benchmark.json")
    payload = load_step_ifc_benchmark_readiness_payload(report)
    assert payload["contract"] == STEP_IFC_GUI_READINESS_CONTRACT
    assert payload["available"] is True
    assert payload["status"] == "failed"
    assert len(payload["case_rows"]) == 2
    bad = [row for row in payload["case_rows"] if row["case_id"] == "bad_step"][0]
    assert bad["artifact_dir"].endswith("bad_step/run_1")
    suggestions = payload["fix_suggestions"]
    assert len(suggestions) == 2
    action_ids = {row["action_id"] for row in suggestions}
    assert "use_native_desktop_runtime" in action_ids
    assert "assign_volume_materials" in action_ids
    assert "apply_fix_suggestion" in payload["actions"]


def test_iter150_missing_report_returns_gui_actions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = load_step_ifc_benchmark_readiness_payload()
    assert payload["available"] is False
    assert payload["status"] == "missing_report"
    assert "run_native_benchmark" in payload["actions"]
