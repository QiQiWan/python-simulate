from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.results import ResultDatabase, build_result_database


@dataclass(slots=True)
class ResultsOverview:
    stage_count: int
    field_count: int
    stages: tuple[str, ...]
    field_labels: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class ResultsService:
    def build_database(self, model: SimulationModel) -> ResultDatabase:
        return build_result_database(model)

    def overview_from_database(self, db: ResultDatabase) -> ResultsOverview:
        return ResultsOverview(
            stage_count=len(db.stage_names()),
            field_count=len(db.fields),
            stages=tuple(db.stage_names()),
            field_labels=tuple(db.field_labels()),
            metadata={
                'model_name': db.model_name,
                'stage_asset_count': int(db.metadata.get('stage_asset_count', 0) or 0),
                'stage_linear_system_plan_count': len(db.metadata.get('stage_linear_system_plans', []) or []),
                'stage_linear_system_diagnostics_count': int(
                    db.metadata.get('stage_linear_system_diagnostics_count', 0) or 0
                ),
                'linear_system_diagnostics_summary': dict(
                    db.metadata.get('linear_system_diagnostics_summary', {}) or {}
                ),
            },
        )

    def build_overview(self, model: SimulationModel) -> ResultsOverview:
        return self.overview_from_database(self.build_database(model))


__all__ = ['ResultsOverview', 'ResultsService']
