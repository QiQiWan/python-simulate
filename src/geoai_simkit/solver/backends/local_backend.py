from __future__ import annotations

from typing import Any

import numpy as np

from .reference_backend import ReferenceBackend


class LocalBackend:
    def __init__(self, backend: Any | None = None) -> None:
        self.backend = backend or ReferenceBackend()

    def solve(self, model, settings):
        return self.backend.solve(model, settings)

    def supports_stage_execution(self, model, settings) -> bool:
        probe = getattr(self.backend, 'supports_stage_execution', None)
        if probe is None:
            return False
        return bool(probe(model, settings))

    def stage_execution_diagnostics(self, model, settings) -> dict[str, object]:
        diagnose = getattr(self.backend, 'stage_execution_diagnostics', None)
        if diagnose is not None:
            return dict(diagnose(model, settings) or {})
        return {
            'backend': type(self.backend).__name__,
            'supported': bool(self.supports_stage_execution(model, settings)),
            'reasons': [],
        }

    def initialize_runtime_state(self, model, settings):
        initializer = getattr(self.backend, 'initialize_runtime_state', None)
        if initializer is None:
            return None
        return initializer(model, settings)

    def begin_stage(self, runtime_state, *, stage_name: str) -> None:
        begin = getattr(self.backend, 'begin_stage', None)
        if begin is not None:
            begin(runtime_state, stage_name=stage_name)

    def advance_stage_increment(
        self,
        model,
        settings,
        runtime_state,
        *,
        stage_name: str,
        active_regions,
        bcs,
        loads,
        load_factor: float,
        increment_index: int,
        increment_count: int,
        stage_metadata=None,
    ):
        advance = getattr(self.backend, 'advance_stage_increment', None)
        if advance is None:
            raise RuntimeError('Backend does not implement stage increment execution.')
        return advance(
            model,
            settings,
            runtime_state,
            stage_name=stage_name,
            active_regions=active_regions,
            bcs=bcs,
            loads=loads,
            load_factor=load_factor,
            increment_index=increment_index,
            increment_count=increment_count,
            stage_metadata=stage_metadata,
        )

    def commit_stage(
        self,
        model,
        runtime_state,
        *,
        stage_name: str,
        increment_result,
        history_rows=None,
        step_trace_rows=None,
    ):
        commit = getattr(self.backend, 'commit_stage', None)
        if commit is None:
            raise RuntimeError('Backend does not implement stage commit.')
        return commit(
            model,
            runtime_state,
            stage_name=stage_name,
            increment_result=increment_result,
            history_rows=history_rows,
            step_trace_rows=step_trace_rows,
        )

    def finalize_runtime_state(self, model, settings, runtime_state):
        finalize = getattr(self.backend, 'finalize_runtime_state', None)
        if finalize is None:
            return model
        return finalize(model, settings, runtime_state)

    def capture_runtime_arrays(self, runtime_state) -> dict[str, np.ndarray]:
        capture = getattr(self.backend, 'capture_runtime_arrays', None)
        if capture is not None:
            return {
                str(name): np.asarray(values)
                for name, values in dict(capture(runtime_state)).items()
            }
        return {}

    def capture_runtime_resume_payload(self, runtime_state) -> dict[str, object]:
        capture = getattr(self.backend, 'capture_runtime_resume_payload', None)
        if capture is not None:
            return dict(capture(runtime_state) or {})
        return {}

    def restore_runtime_state(self, runtime_state, *, arrays=None, payload=None) -> None:
        restore = getattr(self.backend, 'restore_runtime_state', None)
        if restore is not None:
            restore(runtime_state, arrays=dict(arrays or {}), payload=dict(payload or {}))
