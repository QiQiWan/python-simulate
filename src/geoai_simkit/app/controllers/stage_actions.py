from __future__ import annotations

"""GUI-facing stage-planning action controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import project_stage_summary
from geoai_simkit.modules import stage_planning


@dataclass(slots=True)
class StageActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def summary(self) -> dict[str, Any]:
        return project_stage_summary(self.context()).to_dict()

    def rows(self) -> list[dict[str, Any]]:
        return stage_planning.list_project_stages(self.context())

    def compile(self, *stage_ids: str):
        return stage_planning.compile_project_stages(self.context(), stage_ids=stage_ids)

    def active_blocks(self, stage_id: str | None = None) -> set[str]:
        return stage_planning.active_blocks_for_stage(self.context(), stage_id=stage_id)


__all__ = ["StageActionController"]
