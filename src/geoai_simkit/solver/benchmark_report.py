from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geoai_simkit.solver.nonlinear_benchmarks import run_nonlinear_global_benchmark_suite


def build_gui_benchmark_payload(summary: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in summary.get("benchmarks", []) or []:
        name = str(item.get("name", "benchmark"))
        is_capability = "gpu" in name or "occ" in name or "uq" in name
        rows.append(
            {
                "name": name,
                "display_name": name.replace("_", " "),
                "passed": bool(item.get("passed")),
                "status": item.get("status", "reference"),
                "status_level": "capability_probe" if is_capability else "usable_core",
                "notes": "usable_core",
            }
        )
    return {
        "available": True,
        "accepted": bool(summary.get("accepted")),
        "passed_count": int(summary.get("passed_count", 0)),
        "benchmark_count": int(summary.get("benchmark_count", len(rows))),
        "rows": rows,
    }


def write_benchmark_report(out_dir: str | Path = "benchmark_reports") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = run_nonlinear_global_benchmark_suite(out)
    gui_payload = build_gui_benchmark_payload(summary)
    json_path = out / "benchmark_report.json"
    markdown_path = out / "benchmark_report.md"
    gui_payload_path = out / "benchmark_gui_payload.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    markdown_path.write_text(
        "# Solver benchmark report\n\n"
        f"Passed: {summary['passed_count']}/{summary['benchmark_count']}\n",
        encoding="utf-8",
    )
    gui_payload["markdown_path"] = str(markdown_path)
    gui_payload["json_path"] = str(json_path)
    gui_payload["report_dir"] = str(out)
    gui_payload_path.write_text(json.dumps(gui_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {
        **summary,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "gui_payload_path": str(gui_payload_path),
    }


__all__ = ["build_gui_benchmark_payload", "write_benchmark_report"]
