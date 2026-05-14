from __future__ import annotations

"""Undoable semantic/material assignment commands for the phase workbench."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "classify_geometry_entity") and hasattr(document, "assign_entity_material")


def _restore_document(document: Any, backup: dict[str, Any] | None) -> None:
    if backup is None:
        return
    restored = document.__class__.from_dict(backup)
    for field_name in document.__dataclass_fields__:
        setattr(document, field_name, getattr(restored, field_name))


@dataclass(slots=True)
class AssignGeometrySemanticCommand(Command):
    entity_id: str
    semantic_type: str
    material_id: str | None = None
    section_id: str | None = None
    stage_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = "assign_geometry_semantic"
    name: str = "Assign geometry semantic"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Semantic assignment requires GeoProjectDocument")
        self._backup = document.to_dict()
        payload = document.classify_geometry_entity(
            self.entity_id,
            self.semantic_type,
            material_id=self.material_id,
            section_id=self.section_id,
            stage_id=self.stage_id,
            metadata=dict(self.metadata),
        )
        affected = [self.entity_id]
        for key in ("structure", "interface"):
            item = payload.get(key)
            if isinstance(item, dict) and item.get("id"):
                affected.append(str(item["id"]))
        return CommandResult(
            self.id,
            self.name,
            ok=True,
            affected_entities=affected,
            message=f"Assigned {self.semantic_type} to {self.entity_id}",
            metadata=payload,
        )

    def undo(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, f"Undo {self.name}", ok=False, message="Semantic assignment undo requires GeoProjectDocument")
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self.entity_id])


@dataclass(slots=True)
class AssignEntityMaterialCommand(Command):
    entity_id: str
    material_id: str
    category: str | None = None
    id: str = "assign_entity_material"
    name: str = "Assign entity material"
    _backup: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, self.name, ok=False, message="Entity material assignment requires GeoProjectDocument")
        self._backup = document.to_dict()
        payload = document.assign_entity_material(self.entity_id, self.material_id, category=self.category)
        return CommandResult(
            self.id,
            self.name,
            ok=True,
            affected_entities=[self.entity_id, self.material_id],
            message=f"Assigned material {self.material_id} to {self.entity_id}",
            metadata=payload,
        )

    def undo(self, document: Any) -> CommandResult:
        if not _is_geoproject(document):
            return CommandResult(self.id, f"Undo {self.name}", ok=False, message="Entity material assignment undo requires GeoProjectDocument")
        _restore_document(document, self._backup)
        return CommandResult(self.id, f"Undo {self.name}", ok=True, affected_entities=[self.entity_id, self.material_id])


__all__ = ["AssignGeometrySemanticCommand", "AssignEntityMaterialCommand"]
