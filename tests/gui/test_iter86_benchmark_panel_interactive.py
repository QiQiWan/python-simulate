from __future__ import annotations

import json


def test_benchmark_panel_payload_contains_clickable_artifacts(tmp_path, monkeypatch):
    report_dir = tmp_path / "benchmark_reports"
    report_dir.mkdir()
    (report_dir / "benchmark_report.md").write_text("# Report\n", encoding="utf-8")
    (report_dir / "benchmark_report.json").write_text(json.dumps({"accepted": True, "passed_count": 1, "benchmark_count": 1, "benchmarks": [{"name": "a", "passed": True, "solver_backend": "scipy-csr-spsolve"}]}), encoding="utf-8")
    (report_dir / "benchmark_gui_payload.json").write_text(json.dumps({"accepted": True, "passed_count": 1, "benchmark_count": 1, "rows": [{"name": "a", "passed": True}], "markdown_path": str(report_dir / "benchmark_report.md"), "json_path": str(report_dir / "benchmark_report.json"), "report_dir": str(report_dir)}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from geoai_simkit.app.shell.benchmark_panel import load_benchmark_panel_payload
    payload = load_benchmark_panel_payload()
    assert payload["available"] is True
    assert "open_markdown" in payload["actions"]
    assert payload["markdown_path"].endswith("benchmark_report.md")
    assert payload["json_path"].endswith("benchmark_report.json")
