from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from geoai_simkit.pipeline.specs import AnalysisCaseSpec

@dataclass(slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    hint: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class CaseValidationReport:
    ok: bool
    issues: tuple[ValidationIssue, ...]
    summary: dict[str, Any] = field(default_factory=dict)

class AnalysisCaseValidator:
    def __init__(self, case: AnalysisCaseSpec): self.case = case
    def validate(self) -> CaseValidationReport:
        issues: list[ValidationIssue] = []
        if not str(self.case.name).strip(): issues.append(ValidationIssue('error','case_name','Case name is empty.'))
        if not self.case.materials: issues.append(ValidationIssue('warning','materials','No material assignment is defined.'))
        if not (self.case.stages or self.case.mesh_preparation.excavation_steps): issues.append(ValidationIssue('info','stages','No explicit stages; builder will create an initial stage.'))
        return CaseValidationReport(not any(i.level=='error' for i in issues), tuple(issues), {'n_materials': len(self.case.materials), 'n_stages': len(self.case.stages), 'n_excavation_steps': len(self.case.mesh_preparation.excavation_steps)})
