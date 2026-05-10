# Iteration 0.8.68 - External Plugin Entry Points

## Purpose

Promote the internal registry/plugin architecture into an extensible Python entry-point boundary so third-party packages can add mesh generators, solver backends, geology importers, stage compilers, material providers, runtime compilers and postprocessors without modifying GeoAI SimKit source code.

## Entry-point groups

```toml
[project.entry-points."geoai_simkit.mesh_generators"]
my_gmsh = "my_geoai_plugin.mesh:MeshGeneratorPlugin"

[project.entry-points."geoai_simkit.solver_backends"]
my_solver = "my_geoai_plugin.solver:create_backend"

[project.entry-points."geoai_simkit.postprocessors"]
my_report = "my_geoai_plugin.reports:register"
```

Supported groups:

- `geoai_simkit.geology_importers`
- `geoai_simkit.mesh_generators`
- `geoai_simkit.stage_compilers`
- `geoai_simkit.solver_backends`
- `geoai_simkit.material_model_providers`
- `geoai_simkit.runtime_compilers`
- `geoai_simkit.postprocessors`

## Loading model

External plugins are explicit-load by default. Importing `geoai_simkit` does not import third-party plugin packages. Callers can use:

```python
from geoai_simkit.services import discover_external_plugin_entry_points, load_external_plugins

discovery = discover_external_plugin_entry_points()
load_report = load_external_plugins(replace=False)
```

Entry points may expose:

1. a plugin class,
2. a plugin instance,
3. a zero-argument factory returning one or more plugins,
4. a registrar function accepting `ExternalPluginContext` and calling `context.register(plugin)`.

## Governance

`build_module_governance_report()` now embeds external plugin entry-point status in `metadata["external_plugin_entry_points"]`.

## Validation

- `187 passed, 1 skipped`
- Entry-point service remains headless and does not import GUI frameworks.
- Contracts remain dependency-light.
- Virtual entry-point tests verify mesh and solver registration.
