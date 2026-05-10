from __future__ import annotations

"""Preview solve commands for stage-result feedback in the GUI."""

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.commands.command import Command, CommandResult
from geoai_simkit.results.engineering_metrics import build_preview_result_package


def _is_geoproject(document: Any) -> bool:
    return hasattr(document, "geometry_model") and hasattr(document, "result_store")


def _run_geoproject_preview_results(project: Any) -> dict[str, Any]:
    from geoai_simkit.results.result_package import ResultFieldRecord, StageResult
    from geoai_simkit.geoproject import EngineeringMetricRecord, ResultCurve

    project.compile_phase_models()
    project.result_store.phase_results.clear()
    project.result_store.engineering_metrics.clear()
    phase_index = 0
    for stage in project.phases_in_order():
        snapshot = project.phase_manager.phase_state_snapshots.get(stage.id) or project.refresh_phase_snapshot(stage.id)
        result = StageResult(stage_id=stage.id, metadata={"source": "geoproject_preview_results"})
        active_count = len(snapshot.active_volume_ids)
        settlement = -0.5 * phase_index * max(1, len(stage.inactive_blocks))
        wall_deflection = 0.8 * phase_index
        result.metrics["active_volume_count"] = float(active_count)
        result.metrics["max_wall_deflection_mm"] = float(wall_deflection)
        result.metrics["max_settlement_mm"] = float(settlement)
        result.add_field(ResultFieldRecord(name="uz_preview", stage_id=stage.id, association="block", values=[settlement] * active_count, entity_ids=list(snapshot.active_volume_ids), components=1, metadata={"unit": "mm"}))
        project.result_store.phase_results[stage.id] = result
        for key, value in result.metrics.items():
            metric_id = f"{stage.id}:{key}"
            project.result_store.engineering_metrics[metric_id] = EngineeringMetricRecord(id=metric_id, name=key, value=value, unit="mm" if key.endswith("_mm") else "", phase_id=stage.id, metadata={"source": "geoproject_preview_results"})
        phase_index += 1
    for key in ("max_wall_deflection_mm", "max_settlement_mm", "active_volume_count"):
        xs: list[float] = []
        ys: list[float] = []
        for idx, stage in enumerate(project.phases_in_order()):
            result = project.result_store.phase_results.get(stage.id)
            if result and key in result.metrics:
                xs.append(float(idx))
                ys.append(float(result.metrics[key]))
        project.result_store.curves[key] = ResultCurve(id=key, name=key, x=xs, y=ys, x_label="phase", y_label=key)
    project.mark_changed(["result"], action="run_preview_stage_results", affected_entities=list(project.result_store.phase_results))
    return {"stage_count": len(project.result_store.phase_results), "backend": "geoproject_deterministic_preview"}


@dataclass(slots=True)
class RunPreviewStageResultsCommand(Command):
    id: str = "run_preview_stage_results"
    name: str = "Run preview stage results"
    _previous_results: Any = field(default=None, init=False, repr=False)

    def execute(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            self._previous_results = document.result_store.to_dict()
            metadata = _run_geoproject_preview_results(document)
            return CommandResult(
                command_id=self.id,
                name=self.name,
                ok=True,
                message=f"Generated GeoProject preview results for {metadata['stage_count']} phases",
                affected_entities=list(document.result_store.phase_results.keys()),
                metadata=metadata,
            )
        self._previous_results = getattr(document, "results", None)
        document.results = build_preview_result_package(document)
        try:
            document.dirty.mark_results_generated()
        except Exception:
            try:
                document.dirty.result_stale = False
                document.dirty.solve_dirty = False
                document.dirty.messages.append("preview stage results generated")
            except Exception:
                pass
        return CommandResult(
            command_id=self.id,
            name=self.name,
            ok=True,
            message=f"Generated preview results for {len(document.results.stage_results)} stages",
            affected_entities=list(document.results.stage_results.keys()),
            metadata={"stage_count": len(document.results.stage_results), "backend": "deterministic_preview"},
        )

    def undo(self, document: Any) -> CommandResult:
        if _is_geoproject(document):
            if self._previous_results is not None:
                from geoai_simkit.geoproject import ResultStore

                document.result_store = ResultStore.from_dict(self._previous_results)
            document.mark_changed(["result"], action="undo_preview_stage_results")
            return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=True, message="Restored previous GeoProject result state")
        document.results = self._previous_results
        try:
            document.dirty.result_stale = True
            document.dirty.messages.append("undo preview result generation")
        except Exception:
            pass
        return CommandResult(command_id=self.id, name=f"Undo {self.name}", ok=True, message="Restored previous result state")


__all__ = ["RunPreviewStageResultsCommand"]
