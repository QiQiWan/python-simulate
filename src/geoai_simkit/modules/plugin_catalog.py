from __future__ import annotations

"""Unified catalog of module plugin registries."""

from typing import Any


_REQUIRED_DESCRIPTOR_FIELDS = ("key", "label", "category", "version", "available", "capabilities", "health", "metadata")
_REQUIRED_CAPABILITY_FIELDS = ("key", "label", "category", "version", "features", "devices", "supported_inputs", "supported_outputs", "available", "health", "metadata")


def module_plugin_catalog(*, include_external: bool = False, replace_external: bool = False) -> dict[str, Any]:
    from geoai_simkit.geology.importers import get_default_geology_importer_registry
    from geoai_simkit.materials.model_registry import material_model_provider_descriptors
    from geoai_simkit.mesh.generator_registry import mesh_generator_descriptors
    from geoai_simkit.results.postprocessor_registry import postprocessor_descriptors
    from geoai_simkit.runtime_backend_registry import runtime_compiler_descriptors
    from geoai_simkit.solver.backend_registry import solver_backend_capabilities
    from geoai_simkit.stage.compiler_registry import stage_compiler_descriptors

    if include_external:
        from geoai_simkit.services.plugin_entry_points import load_external_plugins

        load_external_plugins(replace=replace_external)

    geology_registry = get_default_geology_importer_registry()
    return {
        "geology_importers": geology_registry.importer_summaries(),
        "mesh_generators": mesh_generator_descriptors(),
        "stage_compilers": stage_compiler_descriptors(),
        "solver_backends": solver_backend_capabilities(),
        "material_model_providers": material_model_provider_descriptors(),
        "runtime_compilers": runtime_compiler_descriptors(),
        "postprocessors": postprocessor_descriptors(),
    }


def validate_plugin_catalog(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate descriptor/capability shape across all plugin registries."""

    catalog = module_plugin_catalog() if catalog is None else catalog
    issues: list[dict[str, Any]] = []
    registry_counts: dict[str, int] = {}
    for registry_key, rows in catalog.items():
        if not isinstance(rows, list) or not rows:
            issues.append({"registry": registry_key, "plugin": None, "issue": "empty_registry"})
            registry_counts[registry_key] = 0
            continue
        registry_counts[registry_key] = len(rows)
        for row in rows:
            if not isinstance(row, dict):
                issues.append({"registry": registry_key, "plugin": None, "issue": "descriptor_not_mapping"})
                continue
            plugin_key = row.get("key")
            for field in _REQUIRED_DESCRIPTOR_FIELDS:
                if field not in row:
                    issues.append({"registry": registry_key, "plugin": plugin_key, "issue": f"missing_descriptor_field:{field}"})
            capability = row.get("capabilities")
            if not isinstance(capability, dict):
                issues.append({"registry": registry_key, "plugin": plugin_key, "issue": "capabilities_not_mapping"})
                continue
            for field in _REQUIRED_CAPABILITY_FIELDS:
                if field not in capability:
                    issues.append({"registry": registry_key, "plugin": plugin_key, "issue": f"missing_capability_field:{field}"})
            health = row.get("health")
            if not isinstance(health, dict):
                issues.append({"registry": registry_key, "plugin": plugin_key, "issue": "health_not_mapping"})
            elif "available" not in health or "dependencies" not in health:
                issues.append({"registry": registry_key, "plugin": plugin_key, "issue": "health_missing_available_or_dependencies"})
    return {
        "suite": "module_plugin_catalog_contract",
        "ok": not issues,
        "registries": registry_counts,
        "issue_count": len(issues),
        "issues": issues,
    }


def external_plugin_entry_point_report(*, load: bool = False, replace: bool = False) -> dict[str, Any]:
    """Return supported external plugin groups plus discovered/loaded entry points."""

    from geoai_simkit.services.plugin_entry_points import discover_external_plugin_entry_points, load_external_plugins, supported_external_plugin_group_dicts

    report = load_external_plugins(replace=replace) if load else discover_external_plugin_entry_points()
    return {
        "suite": "external_plugin_entry_points",
        "ok": bool(report.ok),
        "groups": supported_external_plugin_group_dicts(),
        "discovered_count": int(report.discovered_count),
        "loaded_count": int(report.loaded_count),
        "issue_count": int(report.issue_count),
        "report": report.to_dict(),
    }


def module_plugin_catalog_smoke() -> dict[str, Any]:
    catalog = module_plugin_catalog()
    validation = validate_plugin_catalog(catalog)
    return {
        "suite": "module_plugin_catalog",
        "ok": all(bool(rows) for rows in catalog.values()) and bool(validation.get("ok")),
        "registries": {key: len(value) for key, value in catalog.items()},
        "catalog": catalog,
        "validation": validation,
    }


__all__ = ["external_plugin_entry_point_report", "module_plugin_catalog", "module_plugin_catalog_smoke", "validate_plugin_catalog"]
