from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any, Iterable


def _optional_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except Exception:
        return None


@dataclass(slots=True)
class GpuDeviceInfo:
    alias: str
    name: str
    ordinal: int = -1
    memory_bytes: int = 0

    @property
    def memory_gib(self) -> float:
        return float(self.memory_bytes) / float(1024 ** 3) if self.memory_bytes > 0 else 0.0

    def label(self) -> str:
        if self.memory_bytes > 0:
            return f"{self.alias} ({self.memory_gib:.1f} GiB)"
        return self.alias



def _coerce_memory_bytes(dev: Any) -> int:
    candidates = (
        'total_memory',
        'memory_bytes',
        'mem_total',
        'total_mem',
        'memory_total',
    )
    for attr in candidates:
        value = getattr(dev, attr, None)
        try:
            if value is not None:
                iv = int(value)
                if iv > 0:
                    return iv
        except Exception:
            continue
    return 0



def detect_cuda_devices() -> list[GpuDeviceInfo]:
    wp = _optional_import('warp')
    if wp is None:
        return []
    try:
        if hasattr(wp, 'init'):
            wp.init()
    except Exception:
        return []
    getter = getattr(wp, 'get_cuda_devices', None)
    if not callable(getter):
        return []
    try:
        devices = list(getter())
    except Exception:
        return []
    infos: list[GpuDeviceInfo] = []
    for idx, dev in enumerate(devices):
        alias = str(getattr(dev, 'alias', None) or getattr(dev, 'name', None) or f'cuda:{idx}')
        if not alias.startswith('cuda'):
            alias = f'cuda:{idx}'
        name = str(getattr(dev, 'description', None) or getattr(dev, 'device_name', None) or getattr(dev, 'name', None) or alias)
        infos.append(GpuDeviceInfo(alias=alias, name=name, ordinal=idx, memory_bytes=_coerce_memory_bytes(dev)))
    infos.sort(key=lambda item: (item.memory_bytes, -item.ordinal), reverse=True)
    return infos



def has_cuda() -> bool:
    return bool(detect_cuda_devices())



def choose_cuda_device(requested: str | None, *, round_robin_index: int = 0, allowed_devices: Iterable[str] | None = None) -> str:
    req = str(requested or 'auto').strip().lower()
    devices = detect_cuda_devices()
    allowed = {str(item).strip().lower() for item in (allowed_devices or []) if str(item).strip()}
    if allowed:
        devices = [d for d in devices if d.alias.lower() in allowed]
    aliases = [d.alias.lower() for d in devices]
    if req in {'cpu'}:
        return 'cpu'
    if not devices:
        if req == 'cuda' or req.startswith('cuda:'):
            return 'cuda:0' if req == 'cuda' else req
        return 'cpu'
    if req in {'cuda', 'auto', 'auto-best', 'best'}:
        return devices[0].alias
    if req in {'auto-round-robin', 'round-robin', 'auto-rr'}:
        return devices[int(round_robin_index) % len(devices)].alias
    if req in aliases:
        return devices[aliases.index(req)].alias
    if req.startswith('cuda:'):
        try:
            ordinal = int(req.split(':', 1)[1])
            for dev in devices:
                if dev.ordinal == ordinal:
                    return dev.alias
        except Exception:
            pass
    return devices[0].alias



def describe_cuda_hardware() -> str:
    devices = detect_cuda_devices()
    if not devices:
        return 'CUDA available: no'
    parts = [f'{dev.alias}={dev.name}{f" {dev.memory_gib:.1f}GiB" if dev.memory_bytes > 0 else ""}' for dev in devices]
    return 'CUDA available: yes | GPUs: ' + '; '.join(parts)
