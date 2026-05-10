from __future__ import annotations

from geoai_simkit.solver._benchmark_helpers import benchmark


def run_shell_nafe_ms_reference_suite() -> dict:
    return benchmark("nafems_macneal_shell_reference_suite", case_count=6, max_relative_error=0.12)


__all__ = ["run_shell_nafe_ms_reference_suite"]
