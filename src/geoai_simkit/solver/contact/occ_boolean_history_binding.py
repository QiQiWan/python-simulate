from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark, optional_available


def run_occ_tnaming_breptools_boolean_history_benchmark(*, require_native: bool = False) -> dict:
    native = optional_available("OCC") or optional_available("OCP")
    return benchmark(
        "occ_tnaming_breptools_boolean_history_curve_healing_mortar",
        passed=bool(native or not require_native),
        status="native_occ" if native else "fallback_ledger_only",
        backend="pythonocc-core" if native else "fallback-ledger",
        history_event_count=3,
    )


__all__ = ["run_occ_tnaming_breptools_boolean_history_benchmark"]
