from __future__ import annotations

"""Command stack with undo and redo."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


@dataclass(slots=True)
class CommandStack:
    undo_stack: list[Command] = field(default_factory=list)
    redo_stack: list[Command] = field(default_factory=list)
    history: list[CommandResult] = field(default_factory=list)

    def execute(self, command: Command, document: Any) -> CommandResult:
        result = command.execute(document)
        if result.ok:
            self.undo_stack.append(command)
            self.redo_stack.clear()
        self.history.append(result)
        return result

    def undo(self, document: Any) -> CommandResult:
        if not self.undo_stack:
            return CommandResult(command_id="undo", name="Undo", ok=False, message="No command to undo")
        command = self.undo_stack.pop()
        result = command.undo(document)
        if result.ok:
            self.redo_stack.append(command)
        self.history.append(result)
        return result

    def redo(self, document: Any) -> CommandResult:
        if not self.redo_stack:
            return CommandResult(command_id="redo", name="Redo", ok=False, message="No command to redo")
        command = self.redo_stack.pop()
        result = command.redo(document)
        if result.ok:
            self.undo_stack.append(command)
        self.history.append(result)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "undo_count": len(self.undo_stack),
            "redo_count": len(self.redo_stack),
            "history": [item.to_dict() for item in self.history[-50:]],
        }
