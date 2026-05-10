from __future__ import annotations

from importlib import import_module
from typing import Any

from .dirty_state import DirtyState
from .selection import SelectionRef, SelectionSet
from .engineering_document import EngineeringDocument, MaterialLibraryRecord, engineering_document_from_simulation_model


def __getattr__(name: str) -> Any:
    if name == "GeoProjectDocument":
        value = getattr(import_module("geoai_simkit.geoproject"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'geoai_simkit.document' has no attribute {name!r}")


__all__ = [
    "DirtyState",
    "SelectionRef",
    "SelectionSet",
    "EngineeringDocument",
    "MaterialLibraryRecord",
    "engineering_document_from_simulation_model",
    "GeoProjectDocument",
]
