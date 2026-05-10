from __future__ import annotations

"""Qt-free mesh backend catalog controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.modules.meshing import mesh_generator_descriptors, supported_mesh_generators


@dataclass(slots=True)
class MesherBackendActionController:
    def backend_keys(self) -> list[str]:
        return supported_mesh_generators()

    def backend_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in mesh_generator_descriptors()]


__all__ = ["MesherBackendActionController"]
