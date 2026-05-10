from __future__ import annotations

"""Tool for activating/deactivating selected blocks in a construction stage."""

from dataclasses import dataclass

from geoai_simkit.app.tools.base import ModelingTool, ToolContext
from geoai_simkit.commands.stage_commands import SetStageBlockActivationCommand


@dataclass(slots=True)
class StageActivationTool(ModelingTool):
    stage_id: str
    active: bool
    name: str = "stage_activation"

    def commit(self, context: ToolContext):
        ref = context.document.selection.active
        if ref is None or ref.entity_type != "block":
            return None
        command = SetStageBlockActivationCommand(stage_id=self.stage_id, block_id=ref.entity_id, active=self.active)
        if context.command_stack is not None:
            return context.command_stack.execute(command, context.document)
        return command.execute(context.document)
