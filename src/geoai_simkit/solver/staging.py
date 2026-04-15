from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import AnalysisStage, SimulationModel


@dataclass(slots=True)
class StageContext:
    stage: AnalysisStage
    active_regions: set[str]


class StageManager:
    def __init__(self, model: SimulationModel) -> None:
        self.model = model
        self._known_regions = {region.name for region in model.region_tags} or {binding.region_name for binding in model.materials}
        self._active_regions = set(self._known_regions)

    def _resolve_activation_map(self, stage: AnalysisStage, current_active: set[str]) -> set[str] | None:
        meta = stage.metadata or {}
        amap = meta.get('activation_map')
        if not isinstance(amap, dict) or not amap:
            return None
        mapped = {str(name) for name, enabled in amap.items() if bool(enabled) and str(name) in self._known_regions}
        if mapped:
            return mapped
        return set(current_active)

    def iter_stages(self) -> list[StageContext]:
        if not self.model.stages:
            return [StageContext(stage=AnalysisStage(name="default"), active_regions=set(self._active_regions))]
        contexts: list[StageContext] = []
        active = set(self._active_regions)
        for stage in self.model.stages:
            mapped = self._resolve_activation_map(stage, active)
            if mapped is not None:
                active = set(mapped)
            else:
                active |= {str(name) for name in stage.activate_regions if str(name)}
                active -= set(stage.deactivate_regions)
            contexts.append(StageContext(stage=stage, active_regions=set(active)))
        return contexts
