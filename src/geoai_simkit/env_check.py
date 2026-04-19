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
    group: str = "optional"
    status: str = "ok"
    action: str = ""


_DEPENDENCY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("core", ("numpy", "scipy", "typing_extensions")),
    ("gui", ("pyvista", "PySide6", "pyvistaqt")),
    ("ifc", ("ifcopenshell",)),
    ("meshing", ("meshio", "gmsh")),
    ("gpu", ("warp",)),
    ("dev", ("pytest",)),
)

_GROUP_HINTS = {
    'gui': 'Install GUI extras with: python -m pip install "geoai-simkit[gui]"',
    'ifc': 'Install IFC extras with: python -m pip install "geoai-simkit[ifc]"',
    'meshing': 'Install meshing extras with: python -m pip install "geoai-simkit[meshing]"',
    'gpu': 'Install GPU extras with: python -m pip install "geoai-simkit[gpu]"',
    'dev': 'Install dev extras with: python -m pip install "geoai-simkit[dev]"',
}


def _action_for_failure(name: str, group: str, detail: str) -> str:
    lower = detail.lower()
    if name == 'gmsh' and 'libglu.so.1' in lower:
        return 'Python package is present, but the host is missing libGLU.so.1 / Mesa OpenGL runtime libraries.'
    if 'no module named' in lower:
        return _GROUP_HINTS.get(group, 'Install the matching optional dependency group for this feature.')
    if detail:
        return 'Module import failed after installation; check native libraries, ABI compatibility, or conflicting Qt/OpenGL runtimes.'
    return _GROUP_HINTS.get(group, '')


def _check_module(name: str, group: str) -> DependencyCheck:
    try:
        module = importlib.import_module(name)
        version = getattr(module, '__version__', 'installed')
        return DependencyCheck(name=name, installed=True, detail=str(version), group=group, status='ok', action='')
    except ModuleNotFoundError as exc:
        detail = str(exc)
        return DependencyCheck(name=name, installed=False, detail=detail, group=group, status='missing', action=_action_for_failure(name, group, detail))
    except Exception as exc:
        detail = str(exc)
        return DependencyCheck(name=name, installed=False, detail=detail, group=group, status='broken', action=_action_for_failure(name, group, detail))


def collect_environment_checks() -> list[DependencyCheck]:
    checks: list[DependencyCheck] = []
    for group, modules in _DEPENDENCY_GROUPS:
        for name in modules:
            checks.append(_check_module(name, group))
    return checks


def format_environment_report(checks: Iterable[DependencyCheck]) -> str:
    lines = [f"Python: {sys.version.split()[0]}"]
    current_group = None
    pending_actions: list[str] = []
    for item in checks:
        if item.group != current_group:
            current_group = item.group
            lines.append(f"\n[{current_group}]")
        mark = 'OK' if item.installed else item.status.upper()
        lines.append(f"[{mark:7}] {item.name:<16} {item.detail}")
        if item.action:
            pending_actions.append(f"- {item.name}: {item.action}")
    if pending_actions:
        lines.append("\n[actions]")
        lines.extend(dict.fromkeys(pending_actions))
    return "\n".join(lines)
