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
    try:
        import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime UX helper
        hint = _EXTRA_HINTS.get(extra, _EXTRA_HINTS["all"])
        raise RuntimeError(
            f"{feature} requires the optional dependency '{module_name}'. "
            f"Install the matching extra with: {hint}. "
            f"When working from a local checkout, use the same extra with '-e .[...]'."
        ) from exc
