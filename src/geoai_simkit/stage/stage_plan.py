from __future__ import annotations

"""Staged-construction data model used by visual modeling and solvers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Stage:
    id: str
    name: str
    predecessor_id: str | None = None
    active_blocks: set[str] = field(default_factory=set)
    inactive_blocks: set[str] = field(default_factory=set)
    active_supports: set[str] = field(default_factory=set)
    active_interfaces: set[str] = field(default_factory=set)
    loads: set[str] = field(default_factory=set)
    water_level: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_block_active(self, block_id: str) -> bool:
        if block_id in self.inactive_blocks:
            return False
        if self.active_blocks:
            return block_id in self.active_blocks
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "predecessor_id": self.predecessor_id,
            "active_blocks": sorted(self.active_blocks),
            "inactive_blocks": sorted(self.inactive_blocks),
            "active_supports": sorted(self.active_supports),
            "active_interfaces": sorted(self.active_interfaces),
            "loads": sorted(self.loads),
            "water_level": self.water_level,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class StagePlan:
    stages: dict[str, Stage] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    active_stage_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_stage(self, stage: Stage) -> None:
        self.stages[stage.id] = stage
        if stage.id not in self.order:
            self.order.append(stage.id)
        if self.active_stage_id is None:
            self.active_stage_id = stage.id

    def get(self, stage_id: str | None = None) -> Stage | None:
        if stage_id is None:
            stage_id = self.active_stage_id
        return self.stages.get(str(stage_id)) if stage_id else None

    def set_active(self, stage_id: str) -> Stage:
        if stage_id not in self.stages:
            raise KeyError(f"Stage not found: {stage_id}")
        self.active_stage_id = stage_id
        return self.stages[stage_id]

    def activate_block(self, stage_id: str, block_id: str) -> None:
        stage = self.stages[stage_id]
        stage.inactive_blocks.discard(block_id)
        stage.active_blocks.add(block_id)

    def deactivate_block(self, stage_id: str, block_id: str) -> None:
        stage = self.stages[stage_id]
        stage.active_blocks.discard(block_id)
        stage.inactive_blocks.add(block_id)

    def active_blocks_for_stage(self, all_block_ids: list[str] | tuple[str, ...], stage_id: str | None = None) -> set[str]:
        stage = self.get(stage_id)
        if stage is None:
            return set(all_block_ids)
        if stage.active_blocks:
            return set(stage.active_blocks) - set(stage.inactive_blocks)
        return set(all_block_ids) - set(stage.inactive_blocks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_stage_id": self.active_stage_id,
            "order": list(self.order),
            "stages": [self.stages[sid].to_dict() for sid in self.order if sid in self.stages],
            "metadata": dict(self.metadata),
        }


def stage_plan_from_rows(rows: list[dict[str, Any]], *, all_block_ids: list[str] | tuple[str, ...] = ()) -> StagePlan:
    plan = StagePlan()
    active_so_far: set[str] = set()
    if all_block_ids:
        active_so_far.update(all_block_ids)
    for row in rows:
        sid = str(row.get("name") or row.get("id") or f"stage_{len(plan.order)+1:02d}")
        active_so_far.update(str(v) for v in list(row.get("activate_blocks", []) or []))
        active_so_far.difference_update(str(v) for v in list(row.get("deactivate_blocks", []) or []))
        stage = Stage(
            id=sid,
            name=sid,
            predecessor_id=None if row.get("predecessor") in {None, ""} else str(row.get("predecessor")),
            active_blocks=set(active_so_far),
            inactive_blocks={str(v) for v in list(row.get("deactivate_blocks", []) or [])},
            metadata=dict(row),
        )
        plan.add_stage(stage)
    return plan


__all__ = ["Stage", "StagePlan", "stage_plan_from_rows"]
