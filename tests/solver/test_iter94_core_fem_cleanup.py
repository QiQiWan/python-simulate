from __future__ import annotations


def test_core_fem_matrix_is_layered():
    from geoai_simkit.fem import core_fem_matrix

    matrix = core_fem_matrix()
    keys = {row["key"] for row in matrix}
    assert {"geometry", "mesh", "material", "element", "assembly", "solver", "result"}.issubset(keys)
    assert all(row["layer"] == "core_fem" for row in matrix)
    assert all(row["status"] in {"usable_core", "benchmark_grade", "research_scaffold", "capability_probe", "planned"} for row in matrix)


def test_advanced_matrix_separates_gpu_occ_uq():
    from geoai_simkit.advanced import advanced_matrix

    matrix = advanced_matrix()
    keys = {row["key"] for row in matrix}
    assert {"gpu", "occ", "uq"}.issubset(keys)
    gpu = next(row for row in matrix if row["key"] == "gpu")
    assert gpu["status"] == "capability_probe"
    assert "gpu_resident_ran" in gpu["truthful_gate"]


def test_gui_home_payload_uses_fem_workflow_labels():
    from geoai_simkit.app.completion_matrix import build_gui_home_payload

    payload = build_gui_home_payload()
    labels = [card["label"] for card in payload["cards"]]
    assert labels == ["Modeling", "Mesh", "Solve", "Results", "Benchmark", "Advanced modules"]


def test_benchmark_report_status_normalization():
    from geoai_simkit.solver.benchmark_report import build_gui_benchmark_payload

    summary = {
        "accepted": True,
        "passed_count": 1,
        "benchmark_count": 1,
        "benchmarks": [
            {"name": "status_gated_gpu_cg_gmres_reduction_preconditioner", "passed": True, "status": "status-gated-ready", "gpu_resident_ran": False}
        ],
    }
    payload = build_gui_benchmark_payload(summary)
    row = payload["rows"][0]
    assert "legacy" not in row["display_name"]
    assert row["status_level"] == "capability_probe"
    assert row["notes"] == "usable_core"
