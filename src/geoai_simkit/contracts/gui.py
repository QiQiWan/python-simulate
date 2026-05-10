from __future__ import annotations

"""Dependency-light GUI modularization contracts."""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GuiFileSlimmingMetric:
    """Line/import budget status for a GUI source file."""

    path: str
    line_count: int
    max_lines: int
    import_count: int = 0
    direct_internal_import_count: int = 0
    ok: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line_count": int(self.line_count),
            "max_lines": int(self.max_lines),
            "import_count": int(self.import_count),
            "direct_internal_import_count": int(self.direct_internal_import_count),
            "ok": bool(self.ok),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GuiSlimmingReport:
    """Report used to keep legacy GUI files from growing while controllers absorb actions."""

    ok: bool
    controller_count: int = 0
    metrics: tuple[GuiFileSlimmingMetric, ...] = ()
    controller_modules: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "controller_count": int(self.controller_count),
            "metrics": [item.to_dict() for item in self.metrics],
            "controller_modules": list(self.controller_modules),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


__all__ = ["GuiFileSlimmingMetric", "GuiSlimmingReport"]
