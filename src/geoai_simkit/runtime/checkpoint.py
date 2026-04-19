from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from .compile_config import CheckpointPolicy, RuntimeConfig


def _checkpoint_kind(checkpoint_id: str) -> str:
    token = str(checkpoint_id or '').strip()
    if not token:
        return 'misc'
    return str(token.split('-', 1)[0] or 'misc').strip().lower() or 'misc'


def _normalize_checkpoint_kind_selector(kind: str | None) -> str | None:
    if kind in {None, ''}:
        return None
    token = str(kind).strip().lower().replace('_', '-')
    alias_map = {
        'stage': 'stage',
        'stages': 'stage',
        'failure': 'failure',
        'failures': 'failure',
        'increment': 'increment',
        'increments': 'increment',
    }
    return alias_map.get(token, token)


def checkpoint_policy_from_runtime_config(runtime_config: RuntimeConfig) -> CheckpointPolicy:
    token = str(runtime_config.checkpoint_policy or 'stage-and-failure').strip().lower()
    disabled_tokens = {'', 'none', 'off', 'disabled', 'false', 'no'}
    stage_only_tokens = {'stage', 'stage-only', 'stage_end', 'stage-end'}
    failure_only_tokens = {'failure', 'failure-only'}
    increment_only_tokens = {'increment', 'incremental', 'increment-only'}

    save_at_stage_end = True
    save_at_failure = 'failure' in token
    save_every_n_increments = 0

    if token in disabled_tokens:
        save_at_stage_end = False
        save_at_failure = False
    elif token in stage_only_tokens:
        save_at_stage_end = True
        save_at_failure = False
    elif token in failure_only_tokens:
        save_at_stage_end = False
        save_at_failure = True
    elif token in increment_only_tokens:
        save_at_stage_end = False
        save_at_failure = False
        save_every_n_increments = 1
    elif 'increment' in token:
        save_every_n_increments = 1
        save_at_stage_end = 'stage' in token or 'failure' not in token
        save_at_failure = 'failure' in token

    metadata = dict(runtime_config.metadata or {})
    if metadata.get('checkpoint_save_at_stage_end') is not None:
        save_at_stage_end = bool(metadata.get('checkpoint_save_at_stage_end'))
    if metadata.get('checkpoint_save_at_failure') is not None:
        save_at_failure = bool(metadata.get('checkpoint_save_at_failure'))
    if metadata.get('checkpoint_every_n_increments') is not None:
        save_every_n_increments = max(0, int(metadata.get('checkpoint_every_n_increments') or 0))

    return CheckpointPolicy(
        save_at_stage_end=save_at_stage_end,
        save_at_failure=save_at_failure,
        save_every_n_increments=save_every_n_increments,
        keep_last_n=max(1, int(metadata.get('checkpoint_keep_last_n', 3) or 3)),
        metadata={
            'checkpoint_policy_label': token,
            'retention_scope': 'per-kind',
        },
    )


def _checkpoint_field_labels(
    field_snapshots: list[dict[str, object]] | tuple[dict[str, object], ...] | None,
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    labels: list[str] = []
    stage_field_names: dict[str, list[str]] = {}
    field_array_keys: list[str] = []
    for item in field_snapshots or ():
        entry = dict(item or {})
        name = str(entry.get('name', '') or '')
        if not name:
            continue
        stage_name = entry.get('stage')
        label = name if stage_name in {None, ''} else f'{name}@{stage_name}'
        if label not in labels:
            labels.append(label)
        if stage_name not in {None, ''}:
            stage_key = str(stage_name)
            names = stage_field_names.setdefault(stage_key, [])
            if name not in names:
                names.append(name)
        array_key = str(entry.get('array_key', '') or '')
        if array_key:
            field_array_keys.append(array_key)
    return labels, stage_field_names, field_array_keys


def _checkpoint_array_shapes(arrays: dict[str, np.ndarray] | None) -> dict[str, list[int]]:
    return {
        str(name): list(np.asarray(values).shape)
        for name, values in dict(arrays or {}).items()
    }


@dataclass(slots=True)
class CheckpointManager:
    base_dir: Path
    policy: CheckpointPolicy = field(default_factory=CheckpointPolicy)
    checkpoint_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _delete_checkpoint_assets(self, checkpoint_id: str) -> None:
        stale_path = self.base_dir / f'{checkpoint_id}.json'
        if stale_path.exists():
            stale_path.unlink()
        stale_array_path = self.base_dir / f'{checkpoint_id}.npz'
        if stale_array_path.exists():
            stale_array_path.unlink()

    def _prune_checkpoints(self, checkpoint_kind: str) -> None:
        keep_last_n = max(1, int(self.policy.keep_last_n))
        checkpoint_ids = sorted(
            {
                path.stem
                for path in self.base_dir.glob('*.json')
                if _checkpoint_kind(path.stem) == checkpoint_kind
            }
        )
        stale_ids = checkpoint_ids[:-keep_last_n]
        if not stale_ids:
            return
        for stale_id in stale_ids:
            self._delete_checkpoint_assets(stale_id)
        self.checkpoint_ids = [checkpoint_id for checkpoint_id in self.checkpoint_ids if checkpoint_id not in stale_ids]

    def _checkpoint_json_paths(self) -> list[Path]:
        return sorted(self.base_dir.glob('*.json'))

    def latest_checkpoint_ids(self) -> dict[str, str]:
        latest_by_kind: dict[str, tuple[int, str]] = {}
        for path in self._checkpoint_json_paths():
            checkpoint_id = str(path.stem)
            checkpoint_kind = _checkpoint_kind(checkpoint_id)
            ordering = (int(path.stat().st_mtime_ns), checkpoint_id)
            current = latest_by_kind.get(checkpoint_kind)
            if current is None or ordering > current:
                latest_by_kind[checkpoint_kind] = ordering
        resolved = {
            kind: checkpoint_id
            for kind, (_, checkpoint_id) in latest_by_kind.items()
        }
        if latest_by_kind:
            latest_any = max(latest_by_kind.values())
            resolved['latest'] = str(latest_any[1])
        return resolved

    def latest_checkpoint_id(self, *, kind: str | None = None) -> str | None:
        latest_by_kind = self.latest_checkpoint_ids()
        normalized_kind = _normalize_checkpoint_kind_selector(kind)
        if normalized_kind is None:
            return latest_by_kind.get('latest')
        return latest_by_kind.get(normalized_kind)

    def resolve_checkpoint_id(self, checkpoint_id: str) -> str:
        token = str(checkpoint_id or '').strip()
        if not token:
            raise ValueError('Checkpoint id must not be empty.')
        known_ids = set(self.list_checkpoint_ids())
        if token in known_ids:
            return token

        normalized = token.lower().replace('_', '-')
        alias_kind = None
        if normalized in {'latest', 'last'}:
            alias_kind = None
        elif normalized.startswith('latest-'):
            alias_kind = normalized.removeprefix('latest-')
        elif normalized.startswith('last-'):
            alias_kind = normalized.removeprefix('last-')
        elif normalized.endswith('-latest'):
            alias_kind = normalized.removesuffix('-latest')
        elif normalized.endswith('-last'):
            alias_kind = normalized.removesuffix('-last')

        resolved = self.latest_checkpoint_id(kind=alias_kind)
        if resolved is not None:
            return resolved

        if alias_kind is None:
            raise FileNotFoundError(f'No checkpoint assets were found in {self.base_dir}.')
        raise FileNotFoundError(
            f'No checkpoint assets were found for selector {checkpoint_id!r} in {self.base_dir}.'
        )

    def _write_checkpoint(self, checkpoint_id: str, payload: dict[str, Any]) -> str:
        payload = dict(payload)
        array_payloads = dict(payload.pop('_array_payloads', {}) or {})
        path = self.base_dir / f'{checkpoint_id}.json'
        if array_payloads:
            array_path = self.base_dir / f'{checkpoint_id}.npz'
            np.savez_compressed(
                array_path,
                **{str(name): np.asarray(values) for name, values in array_payloads.items()},
            )
            payload['array_asset'] = array_path.name
            payload['array_keys'] = sorted(str(name) for name in array_payloads)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        self.checkpoint_ids.append(checkpoint_id)
        self._prune_checkpoints(_checkpoint_kind(checkpoint_id))
        return checkpoint_id

    def _record_checkpoint_event(
        self,
        runtime,
        name: str,
        payload: dict[str, object],
    ) -> None:
        runtime.telemetry.record_event(name, payload)
        checkpoint_id = payload.get('checkpoint_id')
        if checkpoint_id is not None:
            runtime.execution_state.last_checkpoint_id = str(checkpoint_id)

    def save_stage_checkpoint(self, runtime, stage_index: int, payload: dict[str, Any] | None = None) -> str:
        checkpoint_id = f'stage-{int(stage_index):03d}'
        started = perf_counter()
        snapshot = payload or runtime.snapshot_state(stage_index=stage_index)
        snapshot = {
            'kind': 'stage',
            'stage_index': int(stage_index),
            **dict(snapshot),
        }
        saved = self._write_checkpoint(checkpoint_id, snapshot)
        self._record_checkpoint_event(
            runtime,
            'checkpoint-save',
            {
                'stage_index': int(stage_index),
                'checkpoint_id': saved,
                'checkpoint_seconds': float(perf_counter() - started),
            },
        )
        return saved

    def save_increment_checkpoint(
        self,
        runtime,
        stage_index: int,
        increment_index: int,
        payload: dict[str, Any] | None = None,
    ) -> str:
        checkpoint_id = f'increment-{int(stage_index):03d}-{int(increment_index):04d}'
        started = perf_counter()
        snapshot = payload or runtime.snapshot_state(stage_index=stage_index, increment_index=increment_index)
        snapshot = {
            'kind': 'increment',
            'stage_index': int(stage_index),
            'increment_index': int(increment_index),
            **dict(snapshot),
        }
        saved = self._write_checkpoint(checkpoint_id, snapshot)
        self._record_checkpoint_event(
            runtime,
            'checkpoint-increment-save',
            {
                'stage_index': int(stage_index),
                'increment_index': int(increment_index),
                'checkpoint_id': saved,
                'checkpoint_seconds': float(perf_counter() - started),
            },
        )
        return saved

    def save_failure_checkpoint(
        self,
        runtime,
        stage_index: int,
        increment_index: int,
        payload: dict[str, Any] | None = None,
    ) -> str:
        checkpoint_id = f'failure-{int(stage_index):03d}-{int(increment_index):04d}'
        started = perf_counter()
        snapshot = payload or runtime.snapshot_state(stage_index=stage_index, increment_index=increment_index)
        snapshot = {
            'kind': 'failure',
            'stage_index': int(stage_index),
            'increment_index': int(increment_index),
            **dict(snapshot),
        }
        saved = self._write_checkpoint(checkpoint_id, snapshot)
        self._record_checkpoint_event(
            runtime,
            'checkpoint-failure-save',
            {
                'stage_index': int(stage_index),
                'increment_index': int(increment_index),
                'checkpoint_id': saved,
                'checkpoint_seconds': float(perf_counter() - started),
            },
        )
        return saved

    def list_checkpoint_ids(self) -> tuple[str, ...]:
        disk_ids = sorted(path.stem for path in self.base_dir.glob('*.json'))
        merged: list[str] = []
        for checkpoint_id in [*self.checkpoint_ids, *disk_ids]:
            token = str(checkpoint_id)
            if token not in merged:
                merged.append(token)
        return tuple(merged)

    def load_checkpoint(self, checkpoint_id: str):
        resolved_checkpoint_id = self.resolve_checkpoint_id(checkpoint_id)
        path = self.base_dir / f'{resolved_checkpoint_id}.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        array_asset = str(payload.get('array_asset') or '')
        if array_asset:
            array_path = self.base_dir / array_asset
            if array_path.exists():
                with np.load(array_path, allow_pickle=False) as arrays:
                    payload['arrays'] = {name: arrays[name] for name in arrays.files}
        payload.setdefault('checkpoint_id', resolved_checkpoint_id)
        payload.setdefault('requested_checkpoint_id', str(checkpoint_id))
        return payload

    def describe_checkpoint(self, checkpoint_id: str) -> dict[str, object]:
        payload = self.load_checkpoint(checkpoint_id)
        execution_state = dict(payload.get('execution_state', {}) or {})
        result_store = dict(payload.get('result_store', {}) or {})
        field_snapshots = list(result_store.get('field_snapshots', []) or [])
        field_labels, stage_field_names, field_array_keys = _checkpoint_field_labels(
            field_snapshots
        )
        arrays = dict(payload.get('arrays', {}) or {})
        missing_field_array_keys = [
            array_key
            for array_key in field_array_keys
            if array_key not in arrays
        ]
        return {
            'checkpoint_id': str(payload.get('checkpoint_id') or checkpoint_id),
            'requested_checkpoint_id': str(payload.get('requested_checkpoint_id') or checkpoint_id),
            'runtime_schema_version': int(payload.get('runtime_schema_version', 0) or 0),
            'kind': str(payload.get('kind', 'unknown')),
            'case_name': payload.get('case_name'),
            'stage_index': payload.get('stage_index'),
            'increment_index': payload.get('increment_index'),
            'partition_count': int(payload.get('partition_count', 0) or 0),
            'array_asset': payload.get('array_asset'),
            'array_keys': list(payload.get('array_keys', []) or []),
            'last_checkpoint_id': execution_state.get('last_checkpoint_id'),
            'committed_stage_index': execution_state.get('committed_stage_index'),
            'committed_increment': execution_state.get('committed_increment'),
            'field_count': len(field_snapshots),
            'field_labels': field_labels,
            'stage_field_names': stage_field_names,
            'field_array_key_count': len(field_array_keys),
            'missing_field_array_keys': missing_field_array_keys,
            'stage_count': len(result_store.get('stage_summaries', []) or []),
            'stage_asset_count': len(result_store.get('stage_assets', []) or []),
            'increment_summary_count': len(result_store.get('increment_summaries', []) or []),
            'resumed_from_checkpoint': result_store.get('metadata', {}).get('resumed_from_checkpoint'),
            'resume_checkpoint_kind': result_store.get('metadata', {}).get('resume_checkpoint_kind'),
            'stage_linear_system_plan_count': len(
                result_store.get('metadata', {}).get('stage_linear_system_plans', []) or []
            ),
            'stage_linear_system_diagnostics_count': int(
                sum(1 for item in result_store.get('stage_assets', []) or [] if item.get('linear_system_diagnostics'))
            ),
            'linear_system_diagnostics_summary': dict(
                result_store.get('metadata', {}).get('linear_system_diagnostics_summary', {}) or {}
            ),
            'last_reduction_summary': dict(payload.get('last_reduction_summary', {}) or {}),
            'array_shapes': _checkpoint_array_shapes(arrays),
        }

    def validate_checkpoint(self, checkpoint_id: str) -> dict[str, object]:
        payload = self.load_checkpoint(checkpoint_id)
        resolved_checkpoint_id = str(payload.get('checkpoint_id') or checkpoint_id)
        requested_checkpoint_id = str(payload.get('requested_checkpoint_id') or checkpoint_id)
        issues: list[str] = []
        warnings: list[str] = []

        runtime_schema_version = int(payload.get('runtime_schema_version', 0) or 0)
        if runtime_schema_version < 2:
            issues.append('runtime_schema_version is missing or too old for distributed runtime checkpoints')

        array_asset = str(payload.get('array_asset') or '')
        array_keys = list(payload.get('array_keys', []) or [])
        arrays = dict(payload.get('arrays', {}) or {})
        if array_asset:
            array_path = self.base_dir / array_asset
            if not array_path.exists():
                issues.append(f'referenced array asset is missing: {array_asset}')
            if array_keys and sorted(arrays.keys()) != sorted(str(item) for item in array_keys):
                issues.append('array_keys do not match the arrays stored in the checkpoint asset')
        elif array_keys:
            warnings.append('array_keys were declared but no array_asset was present')

        if not payload.get('partition_layout_metadata'):
            issues.append('partition_layout_metadata is missing')
        if not payload.get('numbering_metadata'):
            issues.append('numbering_metadata is missing')
        if not payload.get('stage_activation_state'):
            issues.append('stage_activation_state is missing')
        if not payload.get('failure_policy'):
            issues.append('failure_policy is missing')
        if not payload.get('solver_policy'):
            issues.append('solver_policy is missing')
        if not payload.get('telemetry_summary'):
            warnings.append('telemetry_summary is empty')

        result_store = dict(payload.get('result_store', {}) or {})
        result_store_summary = dict(payload.get('result_store_summary', {}) or {})
        field_snapshots = list(result_store.get('field_snapshots', []) or [])
        field_labels, _, field_array_keys = _checkpoint_field_labels(field_snapshots)
        field_count = len(field_snapshots)
        stage_count = len(result_store.get('stage_summaries', []) or [])
        stage_asset_count = len(result_store.get('stage_assets', []) or [])
        stage_linear_system_diagnostics_count = int(
            sum(1 for item in result_store.get('stage_assets', []) or [] if item.get('linear_system_diagnostics'))
        )
        missing_field_array_keys = sorted(
            array_key
            for array_key in field_array_keys
            if array_key not in arrays
        )
        if missing_field_array_keys:
            issues.append(
                'result_store.field_snapshots reference arrays that are missing from the checkpoint asset'
            )
        array_shape_issues: list[str] = []
        total_u = arrays.get('total_u')
        total_u_shape = tuple(np.asarray(total_u).shape) if total_u is not None else None
        if total_u_shape is not None:
            for key in ('stage_start_total_u', 'stage_current_u', 'residual', 'reaction'):
                if key not in arrays:
                    continue
                key_shape = tuple(np.asarray(arrays[key]).shape)
                if key_shape != total_u_shape:
                    issue = f'{key} shape does not match total_u'
                    issues.append(issue)
                    array_shape_issues.append(issue)
        if 'cell_stress' in arrays and 'cell_vm' in arrays:
            cell_stress_shape = tuple(np.asarray(arrays['cell_stress']).shape)
            cell_vm_shape = tuple(np.asarray(arrays['cell_vm']).shape)
            if len(cell_stress_shape) != 2 or len(cell_vm_shape) != 1 or cell_stress_shape[0] != cell_vm_shape[0]:
                issue = 'cell_vm shape does not match cell_stress rows'
                issues.append(issue)
                array_shape_issues.append(issue)
        if result_store_summary:
            if int(result_store_summary.get('field_count', field_count) or 0) != int(field_count):
                issues.append('result_store_summary.field_count does not match result_store.field_snapshots')
            if int(result_store_summary.get('stage_count', stage_count) or 0) != int(stage_count):
                issues.append('result_store_summary.stage_count does not match result_store.stage_summaries')
            if int(result_store_summary.get('stage_asset_count', stage_asset_count) or 0) != int(stage_asset_count):
                issues.append('result_store_summary.stage_asset_count does not match result_store.stage_assets')
            if (
                int(
                    result_store_summary.get(
                        'stage_linear_system_diagnostics_count',
                        stage_linear_system_diagnostics_count,
                    )
                    or 0
                )
                != int(stage_linear_system_diagnostics_count)
            ):
                issues.append(
                    'result_store_summary.stage_linear_system_diagnostics_count does not match stage asset diagnostics'
                )

        result_store_meta = dict(result_store.get('metadata', {}) or {})
        stage_linear_system_plans = list(result_store_meta.get('stage_linear_system_plans', []) or [])
        linear_system_diagnostics_summary = dict(
            result_store_meta.get('linear_system_diagnostics_summary', {}) or {}
        )
        if stage_count > 0 and not stage_linear_system_plans:
            warnings.append('result_store.metadata.stage_linear_system_plans is empty')
        if stage_asset_count > 0 and stage_asset_count > stage_count:
            warnings.append('stage_assets exceed stage_summaries; verify duplicate stage asset capture')
        if stage_asset_count > 0 and stage_linear_system_diagnostics_count == 0:
            warnings.append('stage_assets do not include linear_system_diagnostics')
        if (
            stage_linear_system_diagnostics_count > 0
            and stage_linear_system_diagnostics_count > stage_asset_count
        ):
            issues.append('stage_linear_system_diagnostics_count exceeds stage_asset_count')
        stage_summary_names = {
            str(item.get('stage_name'))
            for item in result_store.get('stage_summaries', []) or []
            if item.get('stage_name')
        }
        stage_asset_names = {
            str(item.get('stage_name'))
            for item in result_store.get('stage_assets', []) or []
            if item.get('stage_name')
        }
        if stage_asset_names and not stage_asset_names.issubset(stage_summary_names):
            issues.append('stage_assets contain stage names not present in stage_summaries')
        if stage_summary_names and stage_asset_count > 0 and not stage_summary_names.issubset(stage_asset_names):
            warnings.append('some stage_summaries do not have matching stage_assets')

        partition_count = int(payload.get('partition_count', 0) or 0)
        partition_layout_count = len(payload.get('partition_layout_metadata', []) or [])
        numbering_count = len(payload.get('numbering_metadata', []) or [])
        if partition_count > 0 and partition_layout_count not in {0, partition_count}:
            issues.append('partition_layout_metadata count does not match partition_count')
        if partition_count > 0 and numbering_count not in {0, partition_count}:
            issues.append('numbering_metadata count does not match partition_count')
        stage_activation_count = len(payload.get('stage_activation_state', []) or [])
        if stage_linear_system_plans and stage_activation_count not in {0, len(stage_linear_system_plans)}:
            issues.append('stage_linear_system_plans count does not match stage_activation_state')
        if linear_system_diagnostics_summary:
            if int(linear_system_diagnostics_summary.get('stage_count', stage_linear_system_diagnostics_count) or 0) not in {
                0,
                stage_linear_system_diagnostics_count,
            }:
                issues.append('linear_system_diagnostics_summary.stage_count does not match stage diagnostics rows')

        return {
            'ok': not issues,
            'checkpoint_id': resolved_checkpoint_id,
            'requested_checkpoint_id': requested_checkpoint_id,
            'kind': str(payload.get('kind', 'unknown')),
            'runtime_schema_version': runtime_schema_version,
            'partition_count': partition_count,
            'array_asset': array_asset or None,
            'array_key_count': len(array_keys),
            'partition_layout_count': partition_layout_count,
            'numbering_count': numbering_count,
            'stage_activation_count': stage_activation_count,
            'field_count': field_count,
            'field_label_count': len(field_labels),
            'stage_count': stage_count,
            'stage_asset_count': stage_asset_count,
            'stage_linear_system_plan_count': len(stage_linear_system_plans),
            'stage_linear_system_diagnostics_count': stage_linear_system_diagnostics_count,
            'missing_field_array_count': len(missing_field_array_keys),
            'missing_field_array_keys': missing_field_array_keys,
            'array_shape_issue_count': len(array_shape_issues),
            'issues': issues,
            'warnings': warnings,
        }
