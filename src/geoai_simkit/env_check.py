from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import Any, Iterable


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
    ("distributed", ("mpi4py",)),
    ("dev", ("pytest",)),
)

_GROUP_HINTS = {
    'gui': 'Install GUI extras with: python -m pip install "geoai-simkit[gui]"',
    'ifc': 'Install IFC extras with: python -m pip install "geoai-simkit[ifc]"',
    'meshing': 'Install meshing extras with: python -m pip install "geoai-simkit[meshing]"',
    'gpu': 'Install GPU extras with: python -m pip install "geoai-simkit[gpu]"',
    'distributed': 'Install distributed extras with: python -m pip install mpi4py',
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




def _module_version(module: Any) -> str:
    return str(getattr(module, '__version__', 'installed'))


def _augment_runtime_detail(name: str, module: Any, detail: str) -> str:
    info = str(detail)
    if name == 'warp':
        try:
            from geoai_simkit.solver.gpu_runtime import describe_cuda_hardware

            info = f"{info}; {describe_cuda_hardware()}"
        except Exception:
            return info
        return info
    if name == 'mpi4py':
        try:
            comm = getattr(module, 'MPI', None)
            world = getattr(comm, 'COMM_WORLD', None)
            if world is not None:
                size = int(world.Get_size())
                rank = int(world.Get_rank())
                return f"{info}; MPI world_size={size}; rank={rank}"
        except Exception:
            return info
    return info


def environment_capability_summary() -> dict[str, Any]:
    checks = collect_environment_checks()
    grouped: dict[str, dict[str, Any]] = {}
    for row in checks:
        payload = grouped.setdefault(
            str(row.group),
            {
                'installed': True,
                'missing': [],
                'broken': [],
                'limited': [],
                'modules': [],
            },
        )
        payload['modules'].append(str(row.name))
        if not row.installed:
            payload['installed'] = False
            status = str(row.status)
            if status == 'broken':
                payload['broken'].append(str(row.name))
            elif status == 'limited':
                payload['limited'].append(str(row.name))
            else:
                payload['missing'].append(str(row.name))
    return {
        'groups': grouped,
        'gpu_hardware': _augment_runtime_detail('warp', object(), 'installed').split('; ', 1)[1] if grouped.get('gpu', {}).get('installed', False) else 'CUDA available: no',
        'distributed_available': bool(grouped.get('distributed', {}).get('installed', False)),
    }

def _check_module(name: str, group: str) -> DependencyCheck:
    try:
        module = importlib.import_module(name)
        if bool(getattr(module, '__geoai_stub__', False)):
            detail = f"{_module_version(module)} (headless compatibility shim; install the real dependency for full functionality)"
            return DependencyCheck(name=name, installed=False, detail=detail, group=group, status='limited', action=_GROUP_HINTS.get(group, 'Install the matching optional dependency group for full functionality.'))
        version = _module_version(module)
        detail = _augment_runtime_detail(name, module, version)
        return DependencyCheck(name=name, installed=True, detail=str(detail), group=group, status='ok', action='')
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
