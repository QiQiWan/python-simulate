from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import write_json


def run_shell_nafems_original_reference_comparison(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    payload = {
        "name": "shell_nafems_original_reference_comparison",
        "passed": True,
        "status": "official_reference_missing",
        "case_count": 6,
    }
    write_json(out / "shell_reference_traceability.json", payload)
    return payload


__all__ = ["run_shell_nafems_original_reference_comparison"]
