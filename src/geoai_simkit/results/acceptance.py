from __future__ import annotations

from typing import Any


def evaluate_result_package_acceptance(package_summary: dict[str, Any] | None = None, *, benchmark_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    package_summary = dict(package_summary or {})
    benchmark_summary = dict(benchmark_summary or {})
    reasons: list[str] = []
    if package_summary.get("engineering_valid") is False:
        reasons.append("engineering_valid=false")
    if benchmark_summary and benchmark_summary.get("accepted") is False:
        reasons.append("benchmark_report_accepted=false")
    accepted = not reasons
    return {"accepted": accepted, "reasons": reasons, "package_summary": package_summary, "benchmark_summary": benchmark_summary}
