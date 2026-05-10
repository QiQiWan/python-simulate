from __future__ import annotations

"""Qt-free compute preference controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services.legacy_gui_backends import recommended_compute_preferences, detect_cuda_devices, default_thread_count


@dataclass(slots=True)
class ComputePreferenceActionController:
    def recommended(self, profile: str = "cpu-safe") -> dict[str, Any]:
        prefs = recommended_compute_preferences(profile, cuda_available=bool(detect_cuda_devices()))
        return {"summary": prefs.summary(cuda_available=bool(detect_cuda_devices())), "metadata": prefs.to_metadata(cuda_available=bool(detect_cuda_devices()))}

    def hardware_summary(self) -> dict[str, Any]:
        return {"cuda_device_count": len(detect_cuda_devices()), "default_thread_count": default_thread_count()}


__all__ = ["ComputePreferenceActionController"]
