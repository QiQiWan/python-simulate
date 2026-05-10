from __future__ import annotations

"""Conservative CUDA/Warp runtime detection helpers.

GPU runtime probing is opt-in to keep CPU-only desktop and CI environments from
accidentally reporting accelerated capability because a stub package is present.
Set GEOAI_ENABLE_GPU_RUNTIME=1 to enable best-effort Warp/CUDA probing.
"""

from dataclasses import dataclass, asdict
from typing import Any
import os


@dataclass(frozen=True, slots=True)
class CudaDeviceInfo:
    index: int
    name: str
    backend: str = "cuda"
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metadata"] = dict(self.metadata or {})
        return data


def gpu_runtime_enabled() -> bool:
    return str(os.environ.get("GEOAI_ENABLE_GPU_RUNTIME", "")).strip().lower() in {"1", "true", "yes", "on"}


def detect_cuda_devices() -> list[dict[str, Any]]:
    if not gpu_runtime_enabled():
        return []
    devices: list[dict[str, Any]] = []
    try:
        import warp as wp  # type: ignore
        if hasattr(wp, "init"):
            wp.init()
        get_devices = getattr(wp, "get_devices", None)
        if callable(get_devices):
            for idx, dev in enumerate(get_devices() or []):
                name = str(getattr(dev, "name", dev))
                if "cuda" in name.lower() or bool(getattr(dev, "is_cuda", False)):
                    devices.append(CudaDeviceInfo(index=idx, name=name, metadata={"source": "warp"}).to_dict())
    except Exception:
        devices = []
    return devices


def describe_cuda_hardware() -> dict[str, Any]:
    devices = detect_cuda_devices()
    return {
        "enabled": gpu_runtime_enabled(),
        "available": bool(devices),
        "device_count": len(devices),
        "devices": devices,
        "note": "Set GEOAI_ENABLE_GPU_RUNTIME=1 to enable CUDA/Warp probing." if not gpu_runtime_enabled() else "Best-effort CUDA/Warp probing completed.",
    }


__all__ = ["CudaDeviceInfo", "gpu_runtime_enabled", "detect_cuda_devices", "describe_cuda_hardware"]
