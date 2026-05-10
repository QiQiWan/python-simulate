from __future__ import annotations

"""Stage activation/deactivation commands."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "geometry_model") and hasattr(document, "phase_manager")


@dataclass(slots=True)
class SetStageBlockActivationCommand(Command):
    stage_id: str
    block_id: str
    active: bool
    id: str = "set_stage_block_activation"
    name: str = "Set stage block activation"
    _previous_active: bool | None = field(default=None, init=False, repr=False)
    _previous_stage_sets: dict[str, set[str]] | None = field(default=None, init=False, repr=False)
    _previous_phase_snapshot: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _previous_explicit_inactive: bool | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _stage_sets(stage: Any) -> dict[str, set[str]]:
        return {
            "active_blocks": set(getattr(stage, "active_blocks", set()) or set()),
            "inactive_blocks": set(getattr(stage, "inactive_blocks", set()) or set()),
        }

    @staticmethod
    def _restore_stage_sets(stage: Any, sets: dict[str, set[str]]) -> None:
        stage.active_blocks.clear()
        stage.active_blocks.update(sets.get("active_blocks", set()))
        stage.inactive_blocks.clear()
        stage.inactive_blocks.update(sets.get("inactive_blocks", set()))

    def _restore_geoproject_snapshot(self, document: Any) -> None:
        if not self._previous_phase_snapshot:
            document.refresh_phase_snapshot(self.stage_id)
            return
        current = document.phase_manager.phase_state_snapshots.get(self.stage_id)
        snapshot_cls = current.__class__ if current is not None else None
        if snapshot_cls is None:
            try:
                from geoai_simkit.geoproject.document import PhaseStateSnapshot
                snapshot_cls = PhaseStateSnapshot
            except Exception:
                snapshot_cls = None
        if snapshot_cls is not None and hasattr(snapshot_cls, "from_dict"):
            document.phase_manager.phase_state_snapshots[self.stage_id] = snapshot_cls.from_dict(self._previous_phase_snapshot)
        else:
            document.refresh_phase_snapshot(self.stage_id)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            phase = document.get_phase(self.stage_id)
            snapshot = document.phase_manager.phase_state_snapshots.get(self.stage_id) or document.refresh_phase_snapshot(self.stage_id)
            self._previous_active = self.block_id in snapshot.active_volume_ids
            self._previous_stage_sets = self._stage_sets(phase)
            self._previous_explicit_inactive = self.block_id in self._previous_stage_sets.get("inactive_blocks", set())
            self._previous_phase_snapshot = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            document.set_phase_volume_activation(self.stage_id, self.block_id, self.active)
            return CommandResult(self.id, self.name, affected_entities=[self.stage_id, self.block_id])
        stage = document.stages.stages[self.stage_id]
        self._previous_active = stage.is_block_active(self.block_id)
        self._previous_stage_sets = self._stage_sets(stage)
        self._previous_explicit_inactive = self.block_id in self._previous_stage_sets.get("inactive_blocks", set())
        if self.active:
            document.stages.activate_block(self.stage_id, self.block_id)
        else:
            document.stages.deactivate_block(self.stage_id, self.block_id)
        document.dirty.mark_stage_changed(f"stage {self.stage_id}: block {self.block_id} active={self.active}")
        return CommandResult(self.id, self.name, affected_entities=[self.stage_id, self.block_id])

    def undo(self, document: Any) -> CommandResult:
        if self._previous_active is None or self._previous_stage_sets is None:
            return CommandResult(self.id, f"Undo {self.name}", ok=False, message="Previous state is unknown")
        if _is_geoproject(document):
            phase = document.get_phase(self.stage_id)
            self._restore_stage_sets(phase, self._previous_stage_sets)
            if self._previous_explicit_inactive is False:
                phase.inactive_blocks.discard(self.block_id)
                phase.active_blocks.add(self.block_id)
                document.refresh_phase_snapshot(self.stage_id)
            else:
                self._restore_geoproject_snapshot(document)
            document.mark_changed(["phase"], action="undo_set_phase_volume_activation", affected_entities=[self.stage_id, self.block_id])
            return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.stage_id, self.block_id])
        stage = document.stages.stages[self.stage_id]
        self._restore_stage_sets(stage, self._previous_stage_sets)
        if self._previous_explicit_inactive is False:
            stage.inactive_blocks.discard(self.block_id)
            stage.active_blocks.add(self.block_id)
        document.dirty.mark_stage_changed(f"undo stage activation: {self.stage_id}/{self.block_id}")
        return CommandResult(self.id, f"Undo {self.name}", affected_entities=[self.stage_id, self.block_id])

    def affected_entities(self) -> list[str]:
        return [self.stage_id, self.block_id]
