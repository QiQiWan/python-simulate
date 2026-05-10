from __future__ import annotations

"""Result postprocessor adapters for existing result stores and packages."""

from typing import Any

from geoai_simkit.contracts import PluginCapability, PluginHealth, ResultRequest, ResultSummary


class ProjectResultSummaryPostProcessor:
    key = "project_result_summary"
    label = "GeoProject result-store summary"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="postprocessor",
        version="1",
        features=("project_result_store", "metric_names", "curve_report_counts"),
        supported_inputs=("GeoProjectDocument", "ProjectReadPort"),
        supported_outputs=("ResultSummary",),
        health=PluginHealth(available=True),
    )

    def summarize(self, request: ResultRequest) -> ResultSummary:
        project = request.source_document()
        store = getattr(project, "result_store", None)
        phase_results = dict(getattr(store, "phase_results", {}) or {})
        metric_names: list[str] = []
        field_count = 0
        for stage in phase_results.values():
            field_count += len(getattr(stage, "fields", {}) or {})
            for metric_name in dict(getattr(stage, "metrics", {}) or {}):
                if metric_name not in metric_names:
                    metric_names.append(metric_name)
        return ResultSummary(
            stage_count=len(phase_results),
            field_count=int(field_count),
            accepted=True,
            metadata={
                "processor": self.key,
                "available": bool(phase_results),
                "project_name": getattr(getattr(project, "project_settings", None), "name", "project"),
                "metric_names": metric_names,
                "curve_count": len(getattr(store, "curves", {}) or {}),
                "report_count": len(getattr(store, "reports", {}) or {}),
                **dict(request.metadata),
            },
        )


class ResultDatabasePostProcessor:
    key = "result_database_summary"
    label = "ResultDatabase summary"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="postprocessor",
        version="1",
        features=("stage_names", "field_labels"),
        supported_inputs=("ResultDatabase",),
        supported_outputs=("ResultSummary",),
        health=PluginHealth(available=True),
    )

    def summarize(self, request: ResultRequest) -> ResultSummary:
        db = request.source
        stage_names = tuple(db.stage_names()) if hasattr(db, "stage_names") else tuple(getattr(db, "stages", ()) or ())
        fields = tuple(getattr(db, "fields", ()) or ())
        return ResultSummary(
            stage_count=len(stage_names),
            field_count=len(fields),
            accepted=True,
            metadata={
                "processor": self.key,
                "model_name": getattr(db, "model_name", None),
                "stages": list(stage_names),
                "field_labels": list(db.field_labels()) if hasattr(db, "field_labels") else [str(item) for item in fields],
                **dict(getattr(db, "metadata", {}) or {}),
                **dict(request.metadata),
            },
        )


class ResultPackagePostProcessor:
    key = "result_package_summary"
    label = "ResultPackage engineering summary"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="postprocessor",
        version="1",
        features=("engineering_metrics", "package_summary"),
        supported_inputs=("ResultPackage",),
        supported_outputs=("ResultSummary",),
        health=PluginHealth(available=True),
    )

    def summarize(self, request: ResultRequest) -> ResultSummary:
        from geoai_simkit.results.engineering_metrics import result_summary

        payload: dict[str, Any] = result_summary(request.source)
        return ResultSummary(
            stage_count=int(payload.get("stage_count", 0) or 0),
            field_count=int(payload.get("field_count", 0) or 0),
            accepted=bool(payload.get("available", True)),
            metadata={"processor": self.key, **payload, **dict(request.metadata)},
        )


__all__ = [
    "ProjectResultSummaryPostProcessor",
    "ResultDatabasePostProcessor",
    "ResultPackagePostProcessor",
]
