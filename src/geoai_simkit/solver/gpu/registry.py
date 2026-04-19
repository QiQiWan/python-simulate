from __future__ import annotations


class KernelRegistry:
    def __init__(self) -> None:
        self._kernels: dict[str, object] = {}

    def register(self, key: str, kernel) -> None:
        self._kernels[str(key)] = kernel

    def get(self, key: str):
        return self._kernels[str(key)]

    def available(self) -> list[str]:
        return sorted(self._kernels)
