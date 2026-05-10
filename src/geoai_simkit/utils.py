from __future__ import annotations

"""Small compatibility utilities shared by optional GUI paths."""

import importlib
from typing import Any


def optional_import(module_name: str) -> Any:
    """Import *module_name* or raise a clear optional-dependency error."""

    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - depends on optional packages
        raise RuntimeError(f"Optional dependency module {module_name!r} is not available: {exc}") from exc


__all__ = ["optional_import"]
