from __future__ import annotations

import importlib
from typing import Any


def optional_import(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise RuntimeError(
            f"Optional dependency '{name}' is required for this feature. Install the matching extra."
        ) from exc
