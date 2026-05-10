from __future__ import annotations

"""Qt-free geometry action controller for legacy GUI slimming."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.services import legacy_gui_backends as backends


@dataclass(slots=True)
class GeometryActionController:
    """Expose geometry/mesher optional dependency state without importing GUI widgets."""

    def optional_dependency_status(self) -> dict[str, Any]:
        return {
            "ifc": {"available": backends.IfcImporter is not None, "error": str(backends._IFC_IMPORT_ERROR) if backends._IFC_IMPORT_ERROR else ""},
            "voxel": {"available": backends.VoxelMesher is not None, "error": str(backends._VOXEL_IMPORT_ERROR) if backends._VOXEL_IMPORT_ERROR else ""},
            "gmsh": {"available": backends.GmshMesher is not None and bool(getattr(backends.GmshMesher, "available", lambda: False)()), "error": str(backends._GMSH_IMPORT_ERROR) if backends._GMSH_IMPORT_ERROR else ""},
        }

    def normalize_element_family(self, value: str) -> str:
        return backends.normalize_element_family(value)


__all__ = ["GeometryActionController"]
