from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import ResultField


@dataclass(slots=True)
class StageResultRecord:
    stage_name: str
    fields: tuple[ResultField, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResultDatabase:
    model_name: str
    fields: tuple[ResultField, ...]
    stages: tuple[StageResultRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def stage_names(self) -> list[str]:
        return [item.stage_name for item in self.stages]

    def field_labels(self) -> list[str]:
        labels: list[str] = []
        for field in self.fields:
            label = field.name if field.stage is None else f'{field.name}@{field.stage}'
            if label not in labels:
                labels.append(label)
        return labels


def build_result_database(model: SimulationModel) -> ResultDatabase:
    stage_map: dict[str, list[ResultField]] = {}
    for field in model.results:
        stage_key = field.stage or '__global__'
        stage_map.setdefault(stage_key, []).append(field)
    stage_records: list[StageResultRecord] = []
    for stage_key, fields in stage_map.items():
        stage_records.append(StageResultRecord(stage_name=stage_key, fields=tuple(fields), metadata={'field_count': len(fields)}))
    return ResultDatabase(model_name=model.name, fields=tuple(model.results), stages=tuple(stage_records), metadata={'result_count': len(model.results)})


def build_result_database_from_runtime_store(runtime_store) -> ResultDatabase:
    from geoai_simkit.results.runtime_adapter import RuntimeResultStoreAdapter

    return RuntimeResultStoreAdapter().from_runtime_store(runtime_store)
