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
                'stage_metrics': list(db.metadata.get('stage_metrics', []) or []),
                'interface_request_count': int(db.metadata.get('interface_request_count', 0) or 0),
                'contact_pair_count': int(db.metadata.get('contact_pair_count', 0) or 0),
            },
        )

    def build_overview(self, model: SimulationModel) -> ResultsOverview:
        return self.overview_from_database(self.build_database(model))

    def stage_package_overview(self, package_path: str) -> dict[str, Any]:
        from geoai_simkit.results import build_stage_package_gui_payload

        payload = build_stage_package_gui_payload(package_path)
        return {
            'available': bool(payload.get('available', False)),
            'case_name': payload.get('case_name'),
            'format': payload.get('format'),
            'package_dir': payload.get('package_dir'),
            'manifest_path': payload.get('manifest_path'),
            'stage_count': int(payload.get('stage_count', 0) or 0),
            'field_count': int(payload.get('field_count', 0) or 0),
            'stage_rows': list(payload.get('stage_rows', []) or []),
            'field_rows': list(payload.get('field_rows', []) or []),
            'contact_panel': dict(payload.get('contact_panel', {}) or {}),
            'release_panel': dict(payload.get('release_panel', {}) or {}),
            'release_load_panel': dict(payload.get('release_load_panel', {}) or {}),
            'geostatic_panel': dict(payload.get('geostatic_panel', {}) or {}),
            'initial_stress_panel': dict(payload.get('initial_stress_panel', {}) or {}),
            'nonlinear_panel': dict(payload.get('nonlinear_panel', {}) or {}),
            'nonlinear_material_residual_panel': dict(payload.get('nonlinear_material_residual_panel', {}) or {}),
            'solver_balance_panel': dict(payload.get('solver_balance_panel', {}) or {}),
            'solver_acceptance_panel': dict(payload.get('solver_acceptance_panel', {}) or {}),
            'preview_panel': dict(payload.get('preview_panel', {}) or {}),
            'gui_index': dict(payload.get('gui_index', {}) or {}),
        }


__all__ = ['ResultsOverview', 'ResultsService']
