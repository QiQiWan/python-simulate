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
        self._active_regions = {region.name for region in model.region_tags} or {binding.region_name for binding in model.materials}

    def iter_stages(self) -> list[StageContext]:
        if not self.model.stages:
            return [StageContext(stage=AnalysisStage(name="default"), active_regions=set(self._active_regions))]
        contexts: list[StageContext] = []
        active = set(self._active_regions)
        for stage in self.model.stages:
            active |= set(stage.activate_regions)
            active -= set(stage.deactivate_regions)
            contexts.append(StageContext(stage=stage, active_regions=set(active)))
        return contexts
