from __future__ import annotations

import json
from pathlib import Path

from geoai_simkit._version import __version__
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload
from geoai_simkit.core.step_ifc_native_benchmark import STEP_IFC_NATIVE_BENCHMARK_CONTRACT
from geoai_simkit.services.step_ifc_native_benchmark import (
    discover_step_ifc_benchmark_cases,
    run_step_ifc_native_benchmark,
    write_step_ifc_benchmark_manifest_template,
)


def _write_embedded_step(path: Path) -> Path:
    payload = {
        "solids": [
            {
                "id": "p85_box_1",
                "name": "P85 benchmark box",
                "bounds": [0, 12, 0, 8, -6, 0],
                "material_id": "alpha_soft_clay",
                "role": "benchmark_volume",
            }
        ]
    }
    path.write_text(
        "ISO-10303-21;\n"
        "HEADER; ENDSEC;\n"
        "DATA;\n"
        f"/* GEOAI_SIMKIT_SOLIDS {json.dumps(payload)} */\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n",
        encoding="utf-8",
    )
    return path


def test_iter149_version_and_gui_payload_expose_p85_benchmark_contract() -> None:
    assert __version__ in {"1.4.9-p85-step-ifc-native-benchmark", "1.5.0-gui-benchmark-readiness", "1.5.1-cad-gui-interaction-materials", "1.5.2-gui-module-matrix-opengl-guard", "1.5.4-viewport-workplane-hover-creation"}
    payload = build_phase_workbench_qt_payload()
    item = payload["geometry_interaction"]["p85_step_ifc_native_benchmark"]
    assert item["contract"] == STEP_IFC_NATIVE_BENCHMARK_CONTRACT
    assert "persistent_naming_stability" in item["validates"]
    assert "mesh_entity_map" in item["validates"]
    assert item["cli"] == "tools/run_step_ifc_native_benchmark.py"


def test_iter149_fallback_dry_run_builds_stable_cad_fem_mesh_and_solver_maps(tmp_path: Path) -> None:
    source = _write_embedded_step(tmp_path / "p85_box.step")
    output = tmp_path / "reports" / "p85_report.json"
    report = run_step_ifc_native_benchmark(source, output_path=output, require_native=False, repeat_count=2, default_element_size=1.2)
    payload = report.to_dict()
    assert payload["contract"] == STEP_IFC_NATIVE_BENCHMARK_CONTRACT
    assert output.exists()
    assert report.ok is True
    assert report.passed_case_count == 1
    case = report.cases[0]
    assert case.ok is True
    assert case.persistent_name_stable is True
    assert case.physical_group_stable is True
    assert case.mesh_entity_map_stable is True
    assert case.solver_region_map_stable is True
    assert case.first_run is not None
    assert case.first_run.topology_summary["solid_count"] >= 1
    assert case.first_run.topology_summary["face_count"] >= 6
    assert case.first_run.mesh_entity_map["metadata"]["planned_physical_groups"]
    assert case.first_run.solver_region_map["ok"] is True
    assert case.first_run.solver_region_map["regions"][0]["material_id"] == "alpha_soft_clay"
    artifacts = Path(report.metadata["artifacts_dir"])
    assert (artifacts / "p85_box" / "run_1" / "cad_fem_preprocessor.json").exists()
    assert (artifacts / "p85_box" / "run_1" / "solver_region_map.json").exists()


def test_iter149_manifest_discovery_and_template(tmp_path: Path) -> None:
    step_path = _write_embedded_step(tmp_path / "case_a.step")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "source_path": step_path.name,
                        "require_native": False,
                        "expected_min_solids": 1,
                        "expected_min_faces": 6,
                        "expected_min_edges": 12,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cases = discover_step_ifc_benchmark_cases(manifest)
    assert len(cases) == 1
    assert cases[0].case_id == "case_a"
    assert Path(cases[0].source_path).is_absolute()
    assert cases[0].expected_min_edges == 12

    report = run_step_ifc_native_benchmark(manifest, output_path=tmp_path / "report.json", require_native=False)
    assert report.ok is True
    assert report.cases[0].first_run is not None
    assert report.cases[0].first_run.topology_summary["edge_count"] >= 12

    template = write_step_ifc_benchmark_manifest_template(tmp_path / "template.json")
    template_payload = json.loads(template.read_text(encoding="utf-8"))
    assert template_payload["contract"] == STEP_IFC_NATIVE_BENCHMARK_CONTRACT
    assert any(row.get("require_lineage") for row in template_payload["cases"])
