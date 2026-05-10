from __future__ import annotations

"""External plugin entry-point discovery and loading service.

External packages can expose GeoAI SimKit plugins with standard Python entry
points.  The service is explicit by default: importing GeoAI SimKit never loads
third-party packages unless callers invoke :func:`load_external_plugins` or set
``GEOAI_AUTOLOAD_EXTERNAL_PLUGINS=1`` through helpers that opt in.
"""

from dataclasses import dataclass, field
import inspect
from importlib import metadata as importlib_metadata
from typing import Any, Callable, Iterable, Mapping, Sequence

from geoai_simkit.contracts.plugins import (
    ExternalPluginEntryPoint,
    ExternalPluginGroupSpec,
    ExternalPluginLoadIssue,
    ExternalPluginLoadRecord,
    ExternalPluginLoadReport,
)


EXTERNAL_PLUGIN_GROUPS: tuple[ExternalPluginGroupSpec, ...] = (
    ExternalPluginGroupSpec(
        group="geoai_simkit.geology_importers",
        registry_key="geology_importers",
        category="geology_importer",
        description="Geological source importers, such as STL, borehole CSV or vendor formats.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.mesh_generators",
        registry_key="mesh_generators",
        category="mesh_generator",
        description="Mesh generators including Gmsh, TetGen, voxel or vendor meshing backends.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.stage_compilers",
        registry_key="stage_compilers",
        category="stage_compiler",
        description="Stage/phase compilers that turn project state into executable phase models.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.solver_backends",
        registry_key="solver_backends",
        category="solver_backend",
        description="CPU/GPU/remote solver backends.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.material_model_providers",
        registry_key="material_model_providers",
        category="material_model_provider",
        description="Material model factories and calibrated constitutive-model packages.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.runtime_compilers",
        registry_key="runtime_compilers",
        category="runtime_compiler",
        description="Runtime bundle compilers and exporters.",
    ),
    ExternalPluginGroupSpec(
        group="geoai_simkit.postprocessors",
        registry_key="postprocessors",
        category="postprocessor",
        description="Result postprocessors, exporters and report builders.",
    ),
)

_GROUPS_BY_NAME = {spec.group: spec for spec in EXTERNAL_PLUGIN_GROUPS}
_GROUPS_BY_REGISTRY = {spec.registry_key: spec for spec in EXTERNAL_PLUGIN_GROUPS}


@dataclass(slots=True)
class ExternalPluginContext:
    """Context passed to registrar-style entry-point callables."""

    group: str
    registry_key: str
    category: str
    replace: bool = False
    registered: list[Any] = field(default_factory=list)

    def register(self, plugin: Any, *, replace: bool | None = None) -> Any:
        # Registrar-style entry points can call context.register(plugin).
        # Actual registry mutation is performed by load_external_plugins so the
        # returned report can count and diagnose registrations consistently.
        self.registered.append(plugin)
        return plugin

    def to_dict(self) -> dict[str, Any]:
        return {"group": self.group, "registry_key": self.registry_key, "category": self.category, "replace": self.replace}


def supported_external_plugin_groups() -> tuple[ExternalPluginGroupSpec, ...]:
    return EXTERNAL_PLUGIN_GROUPS


def supported_external_plugin_group_dicts() -> list[dict[str, Any]]:
    return [item.to_dict() for item in EXTERNAL_PLUGIN_GROUPS]


def _normalise_groups(groups: Iterable[str] | None) -> tuple[ExternalPluginGroupSpec, ...]:
    if groups is None:
        return EXTERNAL_PLUGIN_GROUPS
    out: list[ExternalPluginGroupSpec] = []
    for raw in groups:
        key = str(raw)
        spec = _GROUPS_BY_NAME.get(key) or _GROUPS_BY_REGISTRY.get(key)
        if spec is None:
            raise KeyError(f"Unsupported GeoAI SimKit external plugin group {key!r}")
        if spec not in out:
            out.append(spec)
    return tuple(out)


def _iter_entry_points_for_group(group: str) -> list[Any]:
    eps = importlib_metadata.entry_points()
    if hasattr(eps, "select"):
        return list(eps.select(group=group))
    if isinstance(eps, Mapping):  # pragma: no cover - Python <3.10 compatibility
        return list(eps.get(group, ()))
    return [ep for ep in eps if getattr(ep, "group", "") == group]


def _entry_point_summary(ep: Any, group: str) -> ExternalPluginEntryPoint:
    dist = getattr(ep, "dist", None)
    dist_name = ""
    if dist is not None:
        metadata = getattr(dist, "metadata", None)
        if metadata is not None:
            dist_name = str(metadata.get("Name", ""))
        if not dist_name:
            dist_name = str(getattr(dist, "name", ""))
    value = str(getattr(ep, "value", ""))
    module = str(getattr(ep, "module", ""))
    attr = str(getattr(ep, "attr", ""))
    return ExternalPluginEntryPoint(
        name=str(getattr(ep, "name", "")),
        group=str(getattr(ep, "group", group) or group),
        value=value,
        module=module,
        attr=attr,
        distribution=dist_name,
    )


def discover_external_plugin_entry_points(groups: Iterable[str] | None = None) -> ExternalPluginLoadReport:
    specs = _normalise_groups(groups)
    entry_points: list[ExternalPluginEntryPoint] = []
    for spec in specs:
        for ep in _iter_entry_points_for_group(spec.group):
            entry_points.append(_entry_point_summary(ep, spec.group))
    return ExternalPluginLoadReport(
        ok=True,
        discovered_count=len(entry_points),
        loaded_count=0,
        groups=specs,
        entry_points=tuple(entry_points),
        records=(),
        issues=(),
        metadata={"mode": "discover"},
    )


def _register_plugin(group: str, plugin: Any, *, replace: bool = False) -> None:
    if group == "geoai_simkit.mesh_generators":
        from geoai_simkit.mesh.generator_registry import register_mesh_generator

        register_mesh_generator(plugin, replace=replace)
        return
    if group == "geoai_simkit.solver_backends":
        from geoai_simkit.solver.backend_registry import register_solver_backend

        register_solver_backend(plugin, replace=replace)
        return
    if group == "geoai_simkit.geology_importers":
        from geoai_simkit.geology.importers.registry import get_default_geology_importer_registry

        get_default_geology_importer_registry().register(plugin, replace=replace)
        return
    if group == "geoai_simkit.stage_compilers":
        from geoai_simkit.stage.compiler_registry import register_stage_compiler

        register_stage_compiler(plugin, replace=replace)
        return
    if group == "geoai_simkit.material_model_providers":
        from geoai_simkit.materials.model_registry import register_material_model_provider

        register_material_model_provider(plugin, replace=replace)
        return
    if group == "geoai_simkit.runtime_compilers":
        from geoai_simkit.runtime_backend_registry import register_runtime_compiler_backend

        register_runtime_compiler_backend(plugin, replace=replace)
        return
    if group == "geoai_simkit.postprocessors":
        from geoai_simkit.results.postprocessor_registry import register_postprocessor

        register_postprocessor(plugin, replace=replace)
        return
    raise KeyError(f"Unsupported GeoAI SimKit external plugin group {group!r}")


def _is_plugin_like(obj: Any) -> bool:
    return any(
        hasattr(obj, attr)
        for attr in (
            "key",
            "source_types",
            "can_generate",
            "can_solve",
            "compile",
            "create_model",
            "process",
            "summarize",
        )
    )


def _as_plugin_iter(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        if "plugins" in value:
            return _as_plugin_iter(value["plugins"])
        if "plugin" in value:
            return _as_plugin_iter(value["plugin"])
        return list(value.values())
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    if isinstance(value, Iterable) and not _is_plugin_like(value):
        try:
            return list(value)
        except TypeError:
            return [value]
    return [value]


def _call_entry_point_loaded(obj: Any, context: ExternalPluginContext) -> tuple[list[Any], list[ExternalPluginLoadIssue]]:
    issues: list[ExternalPluginLoadIssue] = []
    if inspect.isclass(obj):
        try:
            return _as_plugin_iter(obj()), issues
        except Exception as exc:  # pragma: no cover - defensive class plugin path
            issues.append(
                ExternalPluginLoadIssue(
                    severity="error",
                    group=context.group,
                    entry_point="<class>",
                    code="entry_point_class_instantiation_failed",
                    message=str(exc),
                    metadata={"class": getattr(obj, "__name__", str(obj))},
                )
            )
            return [], issues
    if _is_plugin_like(obj):
        return [obj], issues
    if callable(obj):
        try:
            signature = inspect.signature(obj)
            required = [
                p
                for p in signature.parameters.values()
                if p.default is p.empty and p.kind in {p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY}
            ]
            if required:
                result = obj(context)
            else:
                result = obj()
            plugins = _as_plugin_iter(result)
            for item in context.registered:
                if item not in plugins:
                    plugins.append(item)
            return plugins, issues
        except Exception as exc:
            issues.append(
                ExternalPluginLoadIssue(
                    severity="error",
                    group=context.group,
                    entry_point=getattr(obj, "__name__", "<callable>"),
                    code="entry_point_callable_failed",
                    message=str(exc),
                    metadata={},
                )
            )
            return [], issues
    return [obj], issues


def load_external_plugins(
    groups: Iterable[str] | None = None,
    *,
    replace: bool = False,
    strict: bool = False,
) -> ExternalPluginLoadReport:
    """Load and register external plugins exposed by supported entry-point groups.

    Entry point callables may return a single plugin, an iterable of plugins, a
    ``{"plugins": [...]}`` mapping, or accept :class:`ExternalPluginContext` and
    call ``context.register(...)`` themselves.  Any registration failure is
    reported in the returned DTO; ``strict=True`` re-raises the first error.
    """

    specs = _normalise_groups(groups)
    records: list[ExternalPluginLoadRecord] = []
    issues: list[ExternalPluginLoadIssue] = []
    entry_points: list[ExternalPluginEntryPoint] = []

    for spec in specs:
        for ep in _iter_entry_points_for_group(spec.group):
            summary = _entry_point_summary(ep, spec.group)
            entry_points.append(summary)
            try:
                loaded = ep.load()
            except Exception as exc:
                issue = ExternalPluginLoadIssue(
                    severity="error",
                    group=spec.group,
                    entry_point=summary.name,
                    code="entry_point_load_failed",
                    message=str(exc),
                    metadata=summary.to_dict(),
                )
                issues.append(issue)
                if strict:
                    raise
                continue

            context = ExternalPluginContext(group=spec.group, registry_key=spec.registry_key, category=spec.category, replace=replace)
            plugins, call_issues = _call_entry_point_loaded(loaded, context)
            for issue in call_issues:
                issues.append(
                    ExternalPluginLoadIssue(
                        severity=issue.severity,
                        group=spec.group,
                        entry_point=summary.name,
                        code=issue.code,
                        message=issue.message,
                        metadata={**dict(issue.metadata), **summary.to_dict()},
                    )
                )
            for plugin in plugins:
                if plugin is None:
                    continue
                if not _is_plugin_like(plugin):
                    issues.append(
                        ExternalPluginLoadIssue(
                            severity="error",
                            group=spec.group,
                            entry_point=summary.name,
                            code="entry_point_returned_non_plugin",
                            message=f"Entry point returned non-plugin object of type {type(plugin).__name__}",
                            metadata=summary.to_dict(),
                        )
                    )
                    if strict:
                        raise TypeError(f"Entry point {summary.name!r} returned non-plugin object {plugin!r}")
                    continue
                plugin_key = str(getattr(plugin, "key", getattr(plugin, "label", summary.name)))
                try:
                    _register_plugin(spec.group, plugin, replace=replace)
                except Exception as exc:
                    issue = ExternalPluginLoadIssue(
                        severity="error",
                        group=spec.group,
                        entry_point=summary.name,
                        code="plugin_registration_failed",
                        message=str(exc),
                        metadata={**summary.to_dict(), "plugin_key": plugin_key},
                    )
                    issues.append(issue)
                    if strict:
                        raise
                    continue
                records.append(
                    ExternalPluginLoadRecord(
                        group=spec.group,
                        entry_point=summary.name,
                        plugin_key=plugin_key,
                        registry_key=spec.registry_key,
                        category=spec.category,
                        replace=replace,
                        metadata=summary.to_dict(),
                    )
                )

    return ExternalPluginLoadReport(
        ok=not any(issue.blocking for issue in issues),
        discovered_count=len(entry_points),
        loaded_count=len(records),
        groups=specs,
        entry_points=tuple(entry_points),
        records=tuple(records),
        issues=tuple(issues),
        metadata={"mode": "load", "replace": bool(replace), "strict": bool(strict)},
    )


__all__ = [
    "EXTERNAL_PLUGIN_GROUPS",
    "ExternalPluginContext",
    "discover_external_plugin_entry_points",
    "load_external_plugins",
    "supported_external_plugin_group_dicts",
    "supported_external_plugin_groups",
]
