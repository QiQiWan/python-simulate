from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass(slots=True)
class TelemetryRecorder:
    level: str = 'standard'
    events: list[dict[str, Any]] = field(default_factory=list)
    _start_time: float = field(default_factory=perf_counter)

    def record_event(self, name: str, payload: dict[str, object]) -> None:
        self.events.append(
            {
                'name': str(name),
                'time_seconds': float(perf_counter() - self._start_time),
                'payload': dict(payload),
            }
        )

    def stage_summary(self, stage_index: int) -> dict[str, object]:
        stage_events = [
            event
            for event in self.events
            if int(event.get('payload', {}).get('stage_index', -1)) == int(stage_index)
        ]
        return {
            'stage_index': int(stage_index),
            'event_count': len(stage_events),
            'event_names': [str(event['name']) for event in stage_events],
        }

    def final_summary(self) -> dict[str, object]:
        counts: dict[str, int] = defaultdict(int)
        timings: dict[str, float] = defaultdict(float)
        for event in self.events:
            name = str(event['name'])
            counts[name] += 1
            payload = dict(event.get('payload', {}))
            for key in (
                'duration_seconds',
                'compile_seconds',
                'runtime_seconds',
                'stage_seconds',
                'checkpoint_seconds',
                'halo_seconds',
            ):
                if key in payload:
                    timings[name] += float(payload[key])
        return {
            'level': self.level,
            'event_count': len(self.events),
            'counts': dict(counts),
            'timings': {key: float(value) for key, value in timings.items()},
            'wallclock_seconds': float(perf_counter() - self._start_time),
        }
