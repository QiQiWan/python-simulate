from __future__ import annotations

"""Stable facade for stage planning and phase compilation."""

from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import StageCompileRequest, StageCompileResult, project_geometry_summary, project_stage_summary
from geoai_simkit.modules.contracts import smoke_from_spec
from geoai_simkit.modules.registry import get_project_module
from geoai_simkit.stage.compiler_registry import get_default_stage_compiler_registry, register_stage_compiler, resolve_stage_compiler, stage_compiler_descriptors
from geoai_simkit.stage.stage_plan import Stage, StagePlan, stage_plan_from_rows

MODULE_KEY = "stage_planning"


def describe_module() -> dict[str, Any]:
    return get_project_module(MODULE_KEY).to_dict()


def compile_project_stages(
    project: Any,
    *,
    stage_ids: tuple[str, ...] | list[str] = (),
    options: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageCompileResult:
    context = as_project_context(project)
    request = StageCompileRequest(
        project=context,
        stage_ids=tuple(str(item) for item in stage_ids),
        options=dict(options or {}),
        metadata=dict(metadata or {}),
    )
    preferred = str(request.options.get("compiler", "auto"))
    compiler = resolve_stage_compiler(request, preferred=preferred)
    return compiler.compile(request)


def list_project_stages(project: Any) -> list[dict[str, Any]]:
    """Return serialisable stage rows through the Project Port first.

    The strict path uses ``ProjectStageSummary`` and only unwraps to the legacy
    phase manager when callers need the richer historical ``to_dict`` payloads.
    """

    context = as_project_context(project)
    summary = project_stage_summary(context)
    if summary.stage_ids:
        project_doc = context.get_project()
        manager = getattr(project_doc, "phase_manager", None)
        stages = getattr(manager, "stages", {}) if manager is not None else {}
        if stages:
            rows = [stages[item].to_dict() for item in summary.stage_ids if item in stages and hasattr(stages[item], "to_dict")]
            if rows:
                return rows
        construction = getattr(manager, "construction_phases", {}) if manager is not None else {}
        initial = getattr(manager, "initial_phase", None) if manager is not None else None
        rows = []
        if initial is not None and hasattr(initial, "to_dict") and str(getattr(initial, "id", "")) in summary.stage_ids:
            rows.append(initial.to_dict())
        rows.extend(value.to_dict() for key, value in getattr(construction, "items", lambda: [])() if str(key) in summary.stage_ids and hasattr(value, "to_dict"))
        if rows:
            return rows
    return [{"id": stage_id, "name": stage_id} for stage_id in summary.stage_ids]


def active_blocks_for_stage(project: Any, stage_id: str | None = None) -> set[str]:
    context = as_project_context(project)
    summary = project_stage_summary(context)
    if stage_id is not None and str(stage_id) in summary.active_blocks_by_stage:
        return set(summary.active_blocks_by_stage[str(stage_id)])
    geometry = project_geometry_summary(context)
    if not summary.active_blocks_by_stage:
        return set(geometry.volume_keys or geometry.block_keys or geometry.keys)
    first_key = str(stage_id or (summary.stage_ids[-1] if summary.stage_ids else ""))
    return set(summary.active_blocks_by_stage.get(first_key, geometry.volume_keys or geometry.block_keys or geometry.keys))


def smoke_check() -> dict[str, Any]:
    return smoke_from_spec(
        get_project_module(MODULE_KEY),
        checks={
            "stage_plan_available": callable(stage_plan_from_rows),
            "stage_model_available": StagePlan is not None and Stage is not None,
            "compiler_registry_available": bool(get_default_stage_compiler_registry().keys()),
        },
    )


__all__ = [
    "Stage",
    "StagePlan",
    "StageCompileRequest",
    "StageCompileResult",
    "get_default_stage_compiler_registry",
    "active_blocks_for_stage",
    "compile_project_stages",
    "describe_module",
    "list_project_stages",
    "register_stage_compiler",
    "smoke_check",
    "stage_compiler_descriptors",
    "stage_plan_from_rows",
]
