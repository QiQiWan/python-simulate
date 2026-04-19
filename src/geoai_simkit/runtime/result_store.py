from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from geoai_simkit.core.types import ResultField


@dataclass(slots=True)
class RuntimeResultStore:
    stage_summaries: list[dict[str, object]] = field(default_factory=list)
    increment_summaries: list[dict[str, object]] = field(default_factory=list)
    field_snapshots: list[dict[str, object]] = field(default_factory=list)
    stage_assets: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def capture_field(self, field: ResultField) -> None:
        self.field_snapshots.append(
            {
                'name': field.name,
                'association': field.association,
                'values': np.asarray(field.values).copy(),
                'components': int(field.components),
                'stage': field.stage,
                'metadata': dict(field.metadata),
            }
        )

    def field_names(self) -> list[str]:
        names: list[str] = []
        for item in self.field_snapshots:
            label = str(item['name']) if item.get('stage') is None else f"{item['name']}@{item['stage']}"
            if label not in names:
                names.append(label)
        return names

    def capture_stage_asset(self, asset: dict[str, object] | None) -> None:
        if not asset:
            return
        self.stage_assets.append(dict(asset))

    def clear(self) -> None:
        self.stage_summaries.clear()
        self.increment_summaries.clear()
        self.field_snapshots.clear()
        self.stage_assets.clear()
        self.metadata.clear()

    def to_result_fields(self) -> list[ResultField]:
        fields: list[ResultField] = []
        for item in self.field_snapshots:
            fields.append(
                ResultField(
                    name=str(item['name']),
                    association=str(item['association']),
                    values=np.asarray(item['values']).copy(),
                    components=int(item.get('components', 1)),
                    stage=item.get('stage'),
                    metadata=dict(item.get('metadata', {})),
                )
            )
        return fields

    def export_checkpoint_payload(self) -> tuple[dict[str, object], dict[str, np.ndarray]]:
        array_payloads: dict[str, np.ndarray] = {}
        field_payloads: list[dict[str, object]] = []
        for index, item in enumerate(self.field_snapshots):
            array_key = f'result_field_{index:04d}'
            array_payloads[array_key] = np.asarray(item['values']).copy()
            field_payloads.append(
                {
                    'name': str(item['name']),
                    'association': str(item['association']),
                    'components': int(item.get('components', 1)),
                    'stage': item.get('stage'),
                    'metadata': dict(item.get('metadata', {})),
                    'array_key': array_key,
                }
            )
        payload = {
            'metadata': dict(self.metadata),
            'stage_summaries': [dict(item) for item in self.stage_summaries],
            'increment_summaries': [
                {
                    **dict(item),
                    'payload': dict(item.get('payload', {})),
                }
                for item in self.increment_summaries
            ],
            'field_snapshots': field_payloads,
            'stage_assets': [dict(item) for item in self.stage_assets],
        }
        return payload, array_payloads

    def restore_checkpoint_payload(
        self,
        payload: dict[str, object] | None,
        arrays: dict[str, np.ndarray] | None = None,
    ) -> None:
        self.clear()
        if not payload:
            return
        arrays = dict(arrays or {})
        self.metadata.update(dict(payload.get('metadata', {}) or {}))
        self.stage_summaries.extend(
            [dict(item) for item in payload.get('stage_summaries', []) or []]
        )
        self.increment_summaries.extend(
            [
                {
                    **dict(item),
                    'payload': dict(item.get('payload', {})),
                }
                for item in payload.get('increment_summaries', []) or []
            ]
        )
        self.stage_assets.extend(
            [dict(item) for item in payload.get('stage_assets', []) or []]
        )
        for item in payload.get('field_snapshots', []) or []:
            entry = dict(item)
            array_key = str(entry.pop('array_key', ''))
            values = np.asarray(arrays.get(array_key, np.empty((0,), dtype=float))).copy()
            self.field_snapshots.append(
                {
                    'name': str(entry.get('name', '')),
                    'association': str(entry.get('association', 'point')),
                    'values': values,
                    'components': int(entry.get('components', 1)),
                    'stage': entry.get('stage'),
                    'metadata': dict(entry.get('metadata', {})),
                }
            )
