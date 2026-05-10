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


__all__ = ["load_benchmark_panel_payload"]
