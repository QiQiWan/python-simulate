from __future__ import annotations

from geoai_simkit.core.types import ResultField
from geoai_simkit.results.database import ResultDatabase, StageResultRecord


class RuntimeResultStoreAdapter:
    def from_runtime_store(self, runtime_store) -> ResultDatabase:
        fields: list[ResultField] = []
        for item in runtime_store.field_snapshots:
            fields.append(
                ResultField(
                    name=str(item['name']),
                    association=str(item['association']),
                    values=item['values'],
                    components=int(item.get('components', 1)),
                    stage=item.get('stage'),
                    metadata=dict(item.get('metadata', {})),
                )
            )

        stage_names = [str(item.get('stage_name')) for item in runtime_store.stage_summaries if item.get('stage_name')]
        stage_asset_rows = [dict(item) for item in getattr(runtime_store, 'stage_assets', []) or []]
        stage_asset_by_name = {
            str(item.get('stage_name')): dict(item)
            for item in stage_asset_rows
            if item.get('stage_name')
        }
        stage_linear_system_plans = list(
            dict(runtime_store.metadata).get('stage_linear_system_plans', []) or []
        )
        linear_system_diagnostics_summary = dict(
            dict(runtime_store.metadata).get('linear_system_diagnostics_summary', {}) or {}
        )
        stage_plan_by_name = {
            str(item.get('stage_name')): dict(item)
            for item in stage_linear_system_plans
            if item.get('stage_name')
        }
        stage_records: list[StageResultRecord] = []
        for stage_name in stage_names:
            stage_fields = tuple(field for field in fields if field.stage == stage_name)
            summary = next(
                (item for item in runtime_store.stage_summaries if item.get('stage_name') == stage_name),
                {},
            )
            asset = dict(stage_asset_by_name.get(stage_name, {}) or {})
            stage_plan = dict(stage_plan_by_name.get(stage_name, {}) or {})
            stage_records.append(
                StageResultRecord(
                    stage_name=stage_name,
                    fields=stage_fields,
                    metadata={
                        **dict(summary),
                        'stage_summary': dict(summary),
                        'stage_asset': asset,
                        'stage_linear_system_plan': (
                            dict(asset.get('stage_linear_system_plan', {}) or {})
                            if asset
                            else stage_plan
                        ),
                        'linear_system_diagnostics': dict(
                            asset.get('linear_system_diagnostics', {}) or {}
                        ),
                        'operator_summary': dict(asset.get('operator_summary', {}) or {}),
                        'partition_linear_systems': list(asset.get('partition_linear_systems', []) or []),
                    },
                )
            )
        return ResultDatabase(
            model_name=str(runtime_store.metadata.get('case_name', 'runtime-model')),
            fields=tuple(fields),
            stages=tuple(stage_records),
            metadata={
                **dict(runtime_store.metadata),
                'result_count': len(fields),
                'stage_asset_count': len(stage_asset_rows),
                'stage_linear_system_diagnostics_count': int(
                    sum(1 for item in stage_asset_rows if item.get('linear_system_diagnostics'))
                ),
                'stage_assets': stage_asset_rows,
                'stage_linear_system_plans': stage_linear_system_plans,
                'linear_system_diagnostics_summary': linear_system_diagnostics_summary,
            },
        )
