from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.solver.gpu_runtime import bind_rank_device, device_capacity_snapshot


@dataclass(slots=True)
class DeviceMemoryPool:
    requested_device: str | None = None
    allocations: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot(self):
        return device_capacity_snapshot(
            allowed_devices=self.metadata.get('allowed_devices'),
        )

    def bind_rank(self, rank: int) -> str:
        return bind_rank_device(
            rank,
            self.requested_device,
            allowed_devices=self.metadata.get('allowed_devices'),
            multi_gpu_mode=self.metadata.get('multi_gpu_mode'),
        )
