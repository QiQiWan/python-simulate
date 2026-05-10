from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_occ_brep_mortar_history_healing_benchmark() -> dict:
    return benchmark(
        "occ_brep_history_healing_mortar_coupling",
        pair_count=2,
        healing={"input_faces": 10, "output_faces": 12},
    )


__all__ = ["run_occ_brep_mortar_history_healing_benchmark"]
