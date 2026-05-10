from __future__ import annotations

"""Stage compiler adapters for existing GeoProjectDocument phase models."""

from geoai_simkit.contracts import PluginCapability, PluginHealth, StageCompileRequest, StageCompileResult


class GeoProjectStageCompilerAdapter:
    key = "geoproject_phase_compiler"
    label = "GeoProject phase compiler"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="stage_compiler",
        version="1",
        features=("phase_models", "stage_filter", "headless"),
        supported_inputs=("GeoProjectDocument", "ProjectReadPort"),
        supported_outputs=("PhaseModel",),
        health=PluginHealth(available=True),
    )

    def compile(self, request: StageCompileRequest) -> StageCompileResult:
        project = request.project_document()
        if project is None or not hasattr(project, "compile_phase_models"):
            raise TypeError("GeoProjectStageCompilerAdapter expects a GeoProjectDocument-like project.")
        phase_models = project.compile_phase_models()
        if request.stage_ids:
            wanted = set(str(item) for item in request.stage_ids)
            phase_models = {key: value for key, value in dict(phase_models).items() if str(key) in wanted}
        return StageCompileResult(
            phase_models=phase_models,
            stage_count=len(phase_models),
            metadata={"compiler": self.key, "requested_stage_ids": list(request.stage_ids), **dict(request.metadata)},
        )


__all__ = ["GeoProjectStageCompilerAdapter"]
