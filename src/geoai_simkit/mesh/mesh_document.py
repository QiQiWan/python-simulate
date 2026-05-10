from __future__ import annotations

"""Tagged mesh document used by GUI, solver compiler and result back-mapping."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap


@dataclass(slots=True)
class MeshQualityReport:
    min_quality: float | None = None
    max_aspect_ratio: float | None = None
    bad_cell_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_quality": self.min_quality,
            "max_aspect_ratio": self.max_aspect_ratio,
            "bad_cell_ids": list(self.bad_cell_ids),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class MeshDocument:
    nodes: list[tuple[float, float, float]] = field(default_factory=list)
    cells: list[tuple[int, ...]] = field(default_factory=list)
    cell_types: list[str] = field(default_factory=list)
    cell_tags: dict[str, list[Any]] = field(default_factory=dict)
    face_tags: dict[str, list[Any]] = field(default_factory=dict)
    node_tags: dict[str, list[Any]] = field(default_factory=dict)
    entity_map: MeshEntityMap = field(default_factory=MeshEntityMap)
    quality: MeshQualityReport = field(default_factory=MeshQualityReport)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    def block_ids(self) -> list[str]:
        return [str(v) for v in self.cell_tags.get("block_id", [])]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "cell_count": self.cell_count,
            "nodes": [list(p) for p in self.nodes],
            "cells": [list(c) for c in self.cells],
            "cell_types": list(self.cell_types),
            "cell_tags": {k: list(v) for k, v in self.cell_tags.items()},
            "face_tags": {k: list(v) for k, v in self.face_tags.items()},
            "node_tags": {k: list(v) for k, v in self.node_tags.items()},
            "entity_map": self.entity_map.to_dict(),
            "quality": self.quality.to_dict(),
            "metadata": dict(self.metadata),
        }
