from __future__ import annotations

"""GUI-facing mesh action controller.

This module is deliberately Qt-free and implementation-light: widgets can call
it without importing meshing internals or solver/runtime code.
"""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import project_mesh_summary
from geoai_simkit.modules import meshing


@dataclass(slots=True)
class MeshActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def summary(self) -> dict[str, Any]:
        return project_mesh_summary(self.context()).to_dict()

    def generate(self, *, mesh_kind: str = "auto", attach: bool = True, **options: Any):
        return meshing.generate_project_mesh(self.context(), mesh_kind=mesh_kind, attach=attach, options=options)


__all__ = ["MeshActionController"]
