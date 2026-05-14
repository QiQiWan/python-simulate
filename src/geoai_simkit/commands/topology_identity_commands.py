from __future__ import annotations

"""Undoable commands for P7 topology identity indexing."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


def _restore_document(document: Any, backup: dict[str, Any] | None) -> None:
    if backup is None:
        return
    restored = document.__class__.from_dict(backup)
    for field_name in document.__dataclass_fields__:
        setattr(document, field_name, getattr(restored, field_name))


@dataclass(slots=True)
class BuildTopologyIdentityIndexCommand(Command):
    """Build the shared ModelEntity/ShapeNode/TopologyElement identity index."""

    require_faces: bool = True
    require_edges: bool = False
    id: str = "build_topology_identity_index"
    name: str = "Build topology identity index"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not hasattr(document, "cad_shape_store"):
            return CommandResult(self.id, self.name, ok=False, message="Topology identity indexing requires GeoProjectDocument with CadShapeStore")
        self._backup = document.to_dict() if hasattr(document, "to_dict") else None
        try:
            from geoai_simkit.services.topology_identity_service import build_topology_identity_index, validate_topology_identity_index

            index = build_topology_identity_index(document, attach=True)
            validation = validate_topology_identity_index(document, require_faces=self.require_faces, require_edges=self.require_edges)
        except Exception as exc:
            return CommandResult(self.id, self.name, ok=False, message=f"Topology identity indexing failed: {type(exc).__name__}: {exc}")
        summary = index.summary()
        return CommandResult(
            self.id,
            self.name,
            ok=bool(validation.get("ok")),
            affected_entities=list(index.lookup_by_topology_id),
            message=f"Topology identity index built: shapes={summary['shape_count']}, topology={summary['topology_count']}, faces={summary['face_count']}, edges={summary['edge_count']}",
            metadata={"index": index.to_dict(), "validation": validation},
        )

    def undo(self, document: Any) -> CommandResult:
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True)


__all__ = ["BuildTopologyIdentityIndexCommand"]
