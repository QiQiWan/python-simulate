from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_occ_native_history_healing_mortar_benchmark() -> dict:
    return benchmark(
        "occ_native_history_healing_mortar",
        healed_face_count=12,
        history_contract={"shape_history": True, "fallback_ledger": True},
    )


__all__ = ["run_occ_native_history_healing_mortar_benchmark"]
