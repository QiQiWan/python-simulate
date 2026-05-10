from __future__ import annotations

from importlib import import_module
from typing import Any

from .mesh_document import MeshDocument, MeshQualityReport
from .mesh_entity_map import MeshEntityMap
from .tagged_mesher import generate_tagged_preview_mesh
from .solid_readiness import validate_solid_analysis_readiness


def __getattr__(name: str) -> Any:
    if name in {"LayeredMeshResult", "generate_layered_volume_mesh"}:
        module = import_module("geoai_simkit.mesh.layered_mesher")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'geoai_simkit.mesh' has no attribute {name!r}")

__all__ = [
    "LayeredMeshResult",
    "MeshDocument",
    "MeshQualityReport",
    "MeshEntityMap",
    "generate_layered_volume_mesh",
    "generate_tagged_preview_mesh",
    "validate_solid_analysis_readiness",
]
