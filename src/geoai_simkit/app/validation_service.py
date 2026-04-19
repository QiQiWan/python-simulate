from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.pipeline import AnalysisCaseSpec, AnalysisCaseValidator


@dataclass(slots=True)
class ValidationOverview:
    ok: bool
    error_count: int
    warning_count: int
    info_count: int
    issues: tuple[dict[str, Any], ...]
    summary: dict[str, Any] = field(default_factory=dict)


class ValidationService:
    def build_overview(self, case: AnalysisCaseSpec) -> ValidationOverview:
        report = AnalysisCaseValidator(case).validate()
        issues = tuple({
            'level': issue.level,
            'code': issue.code,
            'message': issue.message,
            'hint': issue.hint,
            'metadata': dict(issue.metadata),
        } for issue in report.issues)
        return ValidationOverview(
            ok=bool(report.ok),
            error_count=sum(1 for item in report.issues if item.level == 'error'),
            warning_count=sum(1 for item in report.issues if item.level == 'warning'),
            info_count=sum(1 for item in report.issues if item.level == 'info'),
            issues=issues,
            summary=dict(report.summary),
        )


__all__ = ['ValidationOverview', 'ValidationService']
