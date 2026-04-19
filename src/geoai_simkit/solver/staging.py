from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import AnalysisStage, SimulationModel
from geoai_simkit.validation_rules import normalize_region_name


@dataclass(slots=True)
class StageContext:
    stage: AnalysisStage
    active_regions: set[str]


class StageManager:
    def __init__(self, model: SimulationModel) -> None:
        self.model = model
        self._region_lookup = {normalize_region_name(region.name): region.name for region in model.region_tags if str(region.name).strip()}
        if not self._region_lookup:
            self._region_lookup = {normalize_region_name(binding.region_name): binding.region_name for binding in model.materials if str(binding.region_name).strip()}
        self._known_regions = set(self._region_lookup.keys())
        self._active_regions = set(self._region_lookup.values())

    def _resolve_activation_map(self, stage: AnalysisStage, current_active: set[str]) -> set[str] | None:
        meta = stage.metadata or {}
        amap = meta.get('activation_map')
        if not isinstance(amap, dict) or not amap:
            return None
        mapped = {self._region_lookup[norm] for name, enabled in amap.items() if bool(enabled) and (norm := normalize_region_name(name)) in self._region_lookup}
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
