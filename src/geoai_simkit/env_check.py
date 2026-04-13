from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class DependencyCheck:
    name: str
    installed: bool
    detail: str = ""


def _check_module(name: str) -> DependencyCheck:
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "installed")
        return DependencyCheck(name=name, installed=True, detail=str(version))
    except Exception as exc:
        return DependencyCheck(name=name, installed=False, detail=str(exc))


def collect_environment_checks() -> list[DependencyCheck]:
    modules = [
        "numpy",
        "pyvista",
        "PySide6",
        "pyvistaqt",
        "ifcopenshell",
        "warp",
        "scipy",
        "pytest",
    ]
    return [_check_module(name) for name in modules]


def format_environment_report(checks: Iterable[DependencyCheck]) -> str:
    lines = [f"Python: {sys.version.split()[0]}"]
    for item in checks:
        mark = "OK" if item.installed else "MISSING"
        lines.append(f"[{mark:7}] {item.name:<12} {item.detail}")
    return "\n".join(lines)
