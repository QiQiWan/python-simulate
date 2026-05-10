from __future__ import annotations

"""Lightweight stage activation manager used by legacy GUI validation.

This compatibility module keeps GUI/presolve workflows independent from the
newer geoproject phase manager.  It operates on ``core.model.SimulationModel``
objects and exposes deterministic active-region contexts for each analysis
stage.  The implementation is deliberately small and dependency-light so it can
be imported in headless validation paths.
"""

from dataclasses import dataclass
from typing import Iterable

from geoai_simkit.core.model import AnalysisStage, SimulationModel, StageAction
from geoai_simkit.validation_rules import normalize_region_name


@dataclass(frozen=True, slots=True)
class StageContext:
    """Resolved active-region state for one analysis stage."""

    stage: AnalysisStage
    index: int
    active_regions: set[str]
    activated_regions: set[str]
    deactivated_regions: set[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.name,
            "index": int(self.index),
            "active_regions": sorted(self.active_regions),
            "activated_regions": sorted(self.activated_regions),
            "deactivated_regions": sorted(self.deactivated_regions),
        }


class StageManager:
    """Resolve active regions across legacy ``SimulationModel.stages`` rows."""

    def __init__(self, model: SimulationModel) -> None:
        self.model = model
        self._regions = self._region_names()

    def _region_names(self) -> set[str]:
        try:
            self.model.ensure_regions()
        except Exception:
            pass
        names = {normalize_region_name(getattr(region, "name", "")) for region in getattr(self.model, "region_tags", [])}
        return {name for name in names if name}

    @staticmethod
    def _normalized(values: Iterable[object]) -> set[str]:
        return {normalize_region_name(str(item)) for item in values if normalize_region_name(str(item))}

    def _actions_activation_delta(self, actions: Iterable[StageAction]) -> tuple[set[str], set[str]]:
        activate: set[str] = set()
        deactivate: set[str] = set()
        for action in actions or ():
            kind = str(getattr(action, "target_kind", "")).lower()
            target = normalize_region_name(str(getattr(action, "target_id", "")))
            if not target or kind not in {"region", "block", "soil", "volume"}:
                continue
            name = str(getattr(action, "action", "")).lower()
            enabled = bool(getattr(action, "enabled", True))
            if name in {"activate", "enable", "install", "create"} and enabled:
                activate.add(target)
            elif name in {"deactivate", "disable", "excavate", "remove"} or not enabled:
                deactivate.add(target)
        return activate, deactivate

    def _apply_stage(self, active: set[str], stage: AnalysisStage) -> set[str]:
        next_active = set(active)
        meta = getattr(stage, "metadata", {}) or {}
        amap = meta.get("activation_map") if isinstance(meta, dict) else None
        if isinstance(amap, dict):
            for key, value in amap.items():
                name = normalize_region_name(str(key))
                if not name:
                    continue
                if bool(value):
                    next_active.add(name)
                else:
                    next_active.discard(name)
        next_active.update(self._normalized(getattr(stage, "activate_regions", ()) or ()))
        next_active.difference_update(self._normalized(getattr(stage, "deactivate_regions", ()) or ()))
        activate, deactivate = self._actions_activation_delta(getattr(stage, "actions", ()) or ())
        next_active.update(activate)
        next_active.difference_update(deactivate)
        if self._regions:
            # Keep unknown names visible for diagnostics, but prefer known regions
            # when the stage did not specify anything.
            return next_active or set(self._regions)
        return next_active

    def iter_stages(self) -> list[StageContext]:
        stages = list(getattr(self.model, "stages", []) or [])
        if not stages:
            stages = [AnalysisStage(name="initial")]
        active = set(self._regions)
        contexts: list[StageContext] = []
        previous = set(active)
        for idx, stage in enumerate(stages):
            resolved = self._apply_stage(active, stage)
            contexts.append(
                StageContext(
                    stage=stage,
                    index=idx,
                    active_regions=set(resolved),
                    activated_regions=set(resolved - previous),
                    deactivated_regions=set(previous - resolved),
                )
            )
            previous = set(resolved)
            active = set(resolved)
        return contexts

    def active_regions_for_stage(self, stage_name: str) -> set[str]:
        for ctx in self.iter_stages():
            if ctx.stage.name == stage_name:
                return set(ctx.active_regions)
        return set(self._regions)


__all__ = ["StageContext", "StageManager"]
