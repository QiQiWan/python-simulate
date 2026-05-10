from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pyvista as pv


@dataclass(slots=True)
class SceneNode:
    name: str
    mesh: pv.DataSet | None = None
    children: list["SceneNode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, node: "SceneNode") -> None:
        self.children.append(node)

    def to_multiblock(self) -> pv.MultiBlock:
        blocks = pv.MultiBlock()
        if self.mesh is not None:
            blocks[self.name] = self.mesh
        for child in self.children:
            child_blocks = child.to_multiblock()
            for key in child_blocks.keys():
                blocks[f"{child.name}/{key}"] = child_blocks[key]
        return blocks
