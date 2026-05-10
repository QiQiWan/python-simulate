from __future__ import annotations

"""Mapping between engineering entities and mesh tags."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MeshEntityMap:
    block_to_cells: dict[str, list[int]] = field(default_factory=dict)
    face_to_faces: dict[str, list[int]] = field(default_factory=dict)
    interface_to_faces: dict[str, list[int]] = field(default_factory=dict)
    node_sets: dict[str, list[int]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def cells_for_block(self, block_id: str) -> list[int]:
        return list(self.block_to_cells.get(block_id, []))

    def faces_for_entity(self, face_or_interface_id: str) -> list[int]:
        return list(self.face_to_faces.get(face_or_interface_id, self.interface_to_faces.get(face_or_interface_id, [])))

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_to_cells": {k: list(v) for k, v in self.block_to_cells.items()},
            "face_to_faces": {k: list(v) for k, v in self.face_to_faces.items()},
            "interface_to_faces": {k: list(v) for k, v in self.interface_to_faces.items()},
            "node_sets": {k: list(v) for k, v in self.node_sets.items()},
            "metadata": dict(self.metadata),
        }
