from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_complex_wall_soil_mortar_search_benchmark() -> dict:
    return benchmark(
        "complex_wall_soil_mortar_search_and_face_integration",
        pair_count=2,
        pair_reports=[{"pair": "wall-left", "active_gauss_points": 4}, {"pair": "wall-right", "active_gauss_points": 4}],
    )


__all__ = ["run_complex_wall_soil_mortar_search_benchmark"]
