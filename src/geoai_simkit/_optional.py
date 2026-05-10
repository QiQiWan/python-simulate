from __future__ import annotations

from importlib import import_module


_EXTRA_HINTS = {
    "gui": 'python -m pip install "geoai-simkit[gui]"',
    "ifc": 'python -m pip install "geoai-simkit[ifc]"',
    "meshing": 'python -m pip install "geoai-simkit[meshing]"',
    "gpu": 'python -m pip install "geoai-simkit[gpu]"',
    "all": 'python -m pip install "geoai-simkit[all]"',
}


def require_optional_dependency(module_name: str, *, feature: str, extra: str) -> None:
    """Import an optional dependency and reject test-only compatibility shims.

    The project keeps very small PySide6/PyVista shims under ``tests/shims`` so
    headless CI can exercise GUI-adjacent code.  Those shims must never be
    accepted as real runtime dependencies in user launches, otherwise a local
    checkout can appear GUI-capable while silently running without rendering.
    """
    hint = _EXTRA_HINTS.get(extra, _EXTRA_HINTS["all"])
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime UX helper
        raise RuntimeError(
            f"{feature} requires the optional dependency '{module_name}'. "
            f"Install the matching extra with: {hint}. "
            f"When working from a local checkout, use the same extra with '-e .[...]'."
        ) from exc
    if bool(getattr(module, "__geoai_stub__", False)):
        raise RuntimeError(
            f"{feature} requires the real optional dependency '{module_name}', "
            "but a headless test shim was imported. Remove tests/shims from "
            f"PYTHONPATH for normal use and install the matching extra with: {hint}."
        )
