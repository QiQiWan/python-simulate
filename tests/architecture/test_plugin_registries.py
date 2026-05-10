from __future__ import annotations


def test_module_plugin_catalog_exposes_all_replaceable_registry_groups() -> None:
    from geoai_simkit.modules import module_plugin_catalog_smoke

    smoke = module_plugin_catalog_smoke()
    assert smoke["ok"] is True
    registries = smoke["registries"]
    assert registries["geology_importers"] >= 1
    assert registries["mesh_generators"] >= 2
    assert registries["stage_compilers"] >= 1
    assert registries["solver_backends"] >= 1
    assert registries["material_model_providers"] >= 1
    assert registries["runtime_compilers"] >= 1
    assert registries["postprocessors"] >= 1


def test_new_registry_entrypoints_are_dependency_light_and_usable() -> None:
    from geoai_simkit.materials.model_registry import get_default_material_model_registry
    from geoai_simkit.mesh.generator_registry import get_default_mesh_generator_registry
    from geoai_simkit.results.postprocessor_registry import get_default_postprocessor_registry
    from geoai_simkit.runtime_backend_registry import get_default_runtime_compiler_registry
    from geoai_simkit.solver.backend_registry import get_default_solver_backend_registry
    from geoai_simkit.stage.compiler_registry import get_default_stage_compiler_registry

    assert "tagged_preview" in get_default_mesh_generator_registry().keys()
    assert "geoproject_phase_compiler" in get_default_stage_compiler_registry().keys()
    assert "reference_cpu" in get_default_solver_backend_registry().keys()
    assert "builtin_material_models" in get_default_material_model_registry().keys()
    assert "default_runtime_compiler" in get_default_runtime_compiler_registry().keys()
    assert "project_result_summary" in get_default_postprocessor_registry().keys()
