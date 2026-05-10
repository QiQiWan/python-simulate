from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.pipeline import AnalysisCaseSpec, AnalysisCaseValidator


def _headless_summary(case: AnalysisCaseSpec) -> dict[str, Any]:
    stage_roots = [stage.name for stage in case.stages if stage.predecessor in {None, ''}]
    return {
        'case_name': case.name,
        'n_stage_roots': len(stage_roots),
        'stage_roots': stage_roots,
        'n_material_bindings': len(case.materials),
        'n_stages': len(case.stages),
        'n_interfaces': len(case.interfaces),
        'n_structures': len(case.structures),
    }


def _can_fallback_headless(report) -> bool:
    if any(issue.level == 'error' and issue.code != 'prepare_case' for issue in report.issues):
        return False
    prepare_issues = [issue for issue in report.issues if issue.code == 'prepare_case']
    if not prepare_issues:
        return False
    return all(str(issue.metadata.get('exception_type', '')) == 'ModuleNotFoundError' for issue in prepare_issues)


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
        if _can_fallback_headless(report):
            issues = tuple({
                'level': 'warning',
                'code': 'prepare_case_headless',
                'message': 'Prepared a headless validation summary because an optional geometry/visualization dependency is unavailable.',
                'hint': 'Install the full geometry/GUI stack to run mesh-backed validation and viewport previews.',
                'metadata': {'fallback': 'headless-summary'},
            } for _ in [0])
            return ValidationOverview(
                ok=True,
                error_count=0,
                warning_count=len(issues),
                info_count=0,
                issues=issues,
                summary=_headless_summary(case),
            )
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
