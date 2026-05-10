from __future__ import annotations

"""Qt-free GUI material mapping controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts.geotechnical import material_mapping_summary
from geoai_simkit.modules import meshing


@dataclass(slots=True)
class MaterialMappingActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def summary(self) -> dict[str, Any]:
        return material_mapping_summary(self.context()).to_dict()

    def audit(self) -> dict[str, Any]:
        return meshing.audit_region_material_mapping(self.context())


__all__ = ["MaterialMappingActionController"]
