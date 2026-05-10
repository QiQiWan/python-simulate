from __future__ import annotations

import json
from pathlib import Path


def test_benchmark_panel_loads_generated_payload(tmp_path: Path):
    from geoai_simkit.app.shell.benchmark_panel import load_benchmark_panel_payload

    payload_path = tmp_path / "benchmark_gui_payload.json"
    payload_path.write_text(json.dumps({"accepted": True, "passed_count": 2, "benchmark_count": 2, "rows": [{"name": "a", "passed": True}]}), encoding="utf-8")
    payload = load_benchmark_panel_payload(payload_path)
    assert payload["available"] is True
    assert payload["accepted"] is True
    assert payload["passed_count"] == 2


def test_result_package_acceptance_rejects_failed_benchmark():
    from geoai_simkit.results.acceptance import evaluate_result_package_acceptance

    acc = evaluate_result_package_acceptance({"engineering_valid": True}, benchmark_summary={"accepted": False, "passed_count": 1, "benchmark_count": 2})
    assert acc["accepted"] is False
    assert "benchmark_report_accepted=false" in acc["reasons"]
