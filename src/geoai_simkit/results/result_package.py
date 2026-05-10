from __future__ import annotations

"""Result package that maps stage fields and engineering metrics back to objects."""

from dataclasses import dataclass, field
from typing import Any, Literal

FieldAssociation = Literal["node", "cell", "block", "face", "support", "stage"]


@dataclass(slots=True)
class ResultFieldRecord:
    name: str
    stage_id: str | None
    association: FieldAssociation
    values: list[float]
    entity_ids: list[str] = field(default_factory=list)
    components: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stage_id": self.stage_id,
            "association": self.association,
            "values": list(self.values),
            "entity_ids": list(self.entity_ids),
            "components": int(self.components),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class StageResult:
    stage_id: str
    fields: dict[str, ResultFieldRecord] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    support_forces: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_field(self, field_record: ResultFieldRecord) -> None:
        self.fields[field_record.name] = field_record

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "fields": [field.to_dict() for field in self.fields.values()],
            "metrics": dict(self.metrics),
            "support_forces": dict(self.support_forces),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ResultPackage:
    case_name: str
    stage_results: dict[str, StageResult] = field(default_factory=dict)
    entity_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_or_create_stage(self, stage_id: str) -> StageResult:
        if stage_id not in self.stage_results:
            self.stage_results[stage_id] = StageResult(stage_id=stage_id)
        return self.stage_results[stage_id]

    def add_stage_metric(self, stage_id: str, name: str, value: float) -> None:
        self.get_or_create_stage(stage_id).metrics[name] = float(value)

    def metric_curve(self, metric_name: str) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for stage_id, result in self.stage_results.items():
            if metric_name in result.metrics:
                out.append((stage_id, float(result.metrics[metric_name])))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "stage_results": [result.to_dict() for result in self.stage_results.values()],
            "entity_metrics": {k: dict(v) for k, v in self.entity_metrics.items()},
            "metadata": dict(self.metadata),
        }


def result_package_from_stage_metrics(case_name: str, rows: list[dict[str, Any]]) -> ResultPackage:
    package = ResultPackage(case_name=case_name, metadata={"source": "stage_metrics"})
    for row in rows:
        stage_id = str(row.get("stage_name") or row.get("stage") or "stage")
        stage = package.get_or_create_stage(stage_id)
        for key, value in row.items():
            if key in {"stage", "stage_name", "name"}:
                continue
            try:
                stage.metrics[str(key)] = float(value)
            except Exception:
                stage.metadata[str(key)] = value
    return package


__all__ = ["ResultFieldRecord", "StageResult", "ResultPackage", "result_package_from_stage_metrics"]
