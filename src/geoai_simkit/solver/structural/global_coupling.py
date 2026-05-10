from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_shell_bending_benchmark() -> dict:
    return benchmark("shell_bending", formulation="MITC4 reference", tip_w=-0.012)


def run_mindlin_plate_shell_bending_benchmark() -> dict:
    return benchmark("mindlin_plate_shell_bending", formulation="Mindlin plate/shell reference", plate_tip_w=-0.011, shell_tip_w=-0.010)


def run_industrial_shell_bending_locking_benchmark() -> dict:
    return benchmark(
        "industrial_mitc4_shell_bending_locking_local_corotational",
        formulation="MITC4 local-corotational reference",
        tip_values=[-0.021, -0.019, -0.018],
    )


__all__ = [
    "run_shell_bending_benchmark",
    "run_mindlin_plate_shell_bending_benchmark",
    "run_industrial_shell_bending_locking_benchmark",
]
