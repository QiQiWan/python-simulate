from __future__ import annotations

"""Service functions for staged construction editing."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.stage.stage_plan import StagePlan


@dataclass(slots=True)
class StageActivationPreview:
    stage_id: str
    active_blocks: list[str]
    inactive_blocks: list[str]
    active_count: int
    inactive_count: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "active_blocks": list(self.active_blocks),
            "inactive_blocks": list(self.inactive_blocks),
            "active_count": int(self.active_count),
            "inactive_count": int(self.inactive_count),
            "metadata": dict(self.metadata),
        }


class StageActivationService:
    def __init__(self, stage_plan: StagePlan) -> None:
        self.stage_plan = stage_plan

    def activate_block(self, stage_id: str, block_id: str) -> None:
        self.stage_plan.activate_block(stage_id, block_id)

    def deactivate_block(self, stage_id: str, block_id: str) -> None:
        self.stage_plan.deactivate_block(stage_id, block_id)

    def activate_support(self, stage_id: str, support_id: str) -> None:
        stage = self.stage_plan.stages[stage_id]
        stage.active_supports.add(support_id)

    def activate_interface(self, stage_id: str, interface_id: str) -> None:
        stage = self.stage_plan.stages[stage_id]
        stage.active_interfaces.add(interface_id)

    def set_water_level(self, stage_id: str, z: float | None) -> None:
        stage = self.stage_plan.stages[stage_id]
        stage.water_level = None if z is None else float(z)

    def preview_stage(self, stage_id: str, all_block_ids: list[str] | tuple[str, ...]) -> StageActivationPreview:
        active = sorted(self.stage_plan.active_blocks_for_stage(all_block_ids, stage_id))
        inactive = sorted(set(all_block_ids) - set(active))
        stage = self.stage_plan.stages.get(stage_id)
        return StageActivationPreview(
            stage_id=stage_id,
            active_blocks=active,
            inactive_blocks=inactive,
            active_count=len(active),
            inactive_count=len(inactive),
            metadata=dict(stage.metadata if stage is not None else {}),
        )
