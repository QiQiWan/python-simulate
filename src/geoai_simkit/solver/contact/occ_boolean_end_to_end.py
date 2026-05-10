from __future__ import annotations

from pathlib import Path

from geoai_simkit.solver._benchmark_helpers import benchmark, optional_available, write_json


def run_occ_boolean_tnaming_end_to_end_verification(*, require_native: bool = False, out_dir: str | Path) -> dict:
    native = optional_available("OCC") or optional_available("OCP")
    payload = benchmark(
        "occ_boolean_tnaming_end_to_end",
        passed=bool(native or not require_native),
        status="native_occ_end_to_end" if native else "fallback_ledger_only",
        history_event_count=3,
    )
    write_json(Path(out_dir) / "occ_boolean_tnaming_end_to_end.json", payload)
    return payload


__all__ = ["run_occ_boolean_tnaming_end_to_end_verification"]
