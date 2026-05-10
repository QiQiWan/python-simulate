# Iteration 0.8.54 - P2/P3/P4 Modular Boundary Hardening

This iteration continues the modularization roadmap after the P0/P1 contracts and service boundary work.

## P2 - GUI/business service separation

Moved remaining headless/business services out of `geoai_simkit.app` into `geoai_simkit.services`:

- `case_service`
- `preprocess_service`
- `project_lifecycle`
- `results_service`
- `validation_service`

The original `geoai_simkit.app.*` paths remain as thin backward-compatible wrappers, so existing GUI imports and external code keep working while new code can depend on `geoai_simkit.services` directly.

## P3 - Registry/plugin mechanisms

Added or hardened registry-backed plugin entrypoints for replaceable subsystem implementations:

- geology importers: existing importer registry
- mesh generators: `geoai_simkit.mesh.generator_registry`
- stage compilers: `geoai_simkit.stage.compiler_registry`
- solver backends: `geoai_simkit.solver.backend_registry`
- material model providers: `geoai_simkit.materials.model_registry`
- runtime compiler backends: `geoai_simkit.runtime_backend_registry`
- result postprocessors: `geoai_simkit.results.postprocessor_registry`

A unified catalog is available through:

```python
from geoai_simkit.modules import module_plugin_catalog, module_plugin_catalog_smoke
```

## P4 - Architecture boundary tests

Added architecture tests that protect the intended modular boundaries:

- contracts remain dependency-light
- services do not import GUI/rendering/GPU frameworks
- migrated app service paths stay thin compatibility wrappers
- solver/mesh do not import the app layer
- all replaceable registry groups expose default plugins

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -B -m pytest tests -q
96 passed, 1 skipped
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.54
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```
