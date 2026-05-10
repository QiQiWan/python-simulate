from __future__ import annotations

"""Qt-free GPU runtime status controller.

The controller uses the conservative runtime probe only when explicitly called;
GUI widgets can display GPU availability without importing GPU solver kernels.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.solver.gpu_runtime import describe_cuda_hardware


@dataclass(slots=True)
class GpuRuntimeActionController:
    project: Any | None = None

    def summary(self) -> dict[str, Any]:
        return describe_cuda_hardware()


__all__ = ["GpuRuntimeActionController"]
