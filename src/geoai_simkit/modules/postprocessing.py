from __future__ import annotations

"""Stable facade for result postprocessing workflows."""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import ProjectReadPort, ResultRequest, ResultSummary, project_result_store_summary
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module
from geoai_simkit.post import PreviewBuilder
from geoai_simkit.results import ResultDatabase, StageResultRecord, build_result_database
from geoai_simkit.results.engineering_metrics import result_summary
from geoai_simkit.results.result_package import ResultPackage
from geoai_simkit.results.postprocessor_registry import get_default_postprocessor_registry, postprocessor_descriptors, register_postprocessor, resolve_postprocessor

MODULE_KEY = "postprocessing"


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def postprocessor_registry():
    return get_default_postprocessor_registry()


def summarize_results(
    source: Any,
    *,
    processor: str = "auto",
    stage_ids: tuple[str, ...] | list[str] = (),
    fields: tuple[str, ...] | list[str] = (),
    metadata: dict[str, Any] | None = None,
) -> ResultSummary:
    if hasattr(source, "snapshot") and hasattr(source, "get_project"):
        request_source = source
    elif hasattr(source, "result_store"):
        request_source = as_project_context(source)
    else:
        request_source = source
    request = ResultRequest(
        source=request_source,
        stage_ids=tuple(str(item) for item in stage_ids),
        fields=tuple(str(item) for item in fields),
        metadata=dict(metadata or {}),
    )
    return resolve_postprocessor(request, preferred=processor).summarize(request)


def build_result_database_for_model(model: Any) -> ResultDatabase:
    return build_result_database(model)


def build_project_result_summary(project: Any) -> dict[str, Any]:
    port_summary = project_result_store_summary(as_project_context(project)).to_dict()
    summary = summarize_results(project, processor="project_result_summary")
    payload = dict(summary.metadata)
    payload.setdefault("available", summary.stage_count > 0 or port_summary.get("stage_count", 0) > 0)
    payload.setdefault("phase_count", summary.stage_count or port_summary.get("stage_count", 0))
    payload.setdefault("field_count", summary.field_count or port_summary.get("field_count", 0))
    payload.setdefault("port_summary", port_summary)
    return payload


def build_result_package_summary(package: ResultPackage | None) -> dict[str, Any]:
    return result_summary(package)


def create_preview_builder() -> PreviewBuilder:
    return PreviewBuilder()


def smoke_check() -> dict[str, Any]:
    record = StageResultRecord(stage_name="stage-1", field_count=1)
    package = ResultPackage(case_name="post-module-smoke")
    package.add_stage_metric("stage-1", "max_displacement", 0.01)
    summary = build_result_package_summary(package)
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "stage_record_available": record.to_dict()["field_count"] == 1,
            "summary_available": bool(summary.get("available")),
            "preview_builder_available": isinstance(create_preview_builder(), PreviewBuilder),
            "postprocessor_registry_available": bool(postprocessor_registry().keys()),
        },
    )


__all__ = [
    "PreviewBuilder",
    "ResultDatabase",
    "ResultRequest",
    "ResultSummary",
    "build_project_result_summary",
    "build_result_database_for_model",
    "build_result_package_summary",
    "create_preview_builder",
    "postprocessor_descriptors",
    "postprocessor_registry",
    "register_postprocessor",
    "describe_module",
    "smoke_check",
    "summarize_results",
]
