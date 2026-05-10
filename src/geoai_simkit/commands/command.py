from __future__ import annotations

"""Undoable command interface for visual model editing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CommandResult:
    command_id: str
    name: str
    ok: bool = True
    message: str = ""
    affected_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "name": self.name,
            "ok": bool(self.ok),
            "message": self.message,
            "affected_entities": list(self.affected_entities),
            "metadata": dict(self.metadata),
        }


class Command(ABC):
    id: str = "command"
    name: str = "Command"

    @abstractmethod
    def execute(self, document: Any) -> CommandResult:
        pass

    @abstractmethod
    def undo(self, document: Any) -> CommandResult:
        pass

    def redo(self, document: Any) -> CommandResult:
        return self.execute(document)

    def affected_entities(self) -> list[str]:
        return []
