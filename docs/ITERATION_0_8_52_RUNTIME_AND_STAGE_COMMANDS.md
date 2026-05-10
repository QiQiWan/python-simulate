# Iteration 0.8.52 - Runtime and Stage Command Hardening

## Scope

This iteration hardens the dependency-light runtime contract and fixes staged block activation undo/redo behavior in the visual modeling workflow.

## Changes

- `SetStageBlockActivationCommand` now records previous stage activation sets and handles inherited-active blocks separately from pre-existing explicit inactive blocks.
- Added regression tests for inherited-active undo/redo and explicit inactive preservation.
- Added `geoai_simkit.runtime` with public `CompileConfig`, `RuntimeConfig`, `SolverPolicy`, `RuntimeCompiler`, and `RuntimeBundleManager` contracts.
- Added conservative `geoai_simkit.solver.gpu_runtime` detection; CUDA/Warp probing is disabled unless `GEOAI_ENABLE_GPU_RUNTIME=1` is set.
- Extended `SolverSettings` with sparse preference, cutback, device and thread-count fields, and preserved nonlinear tolerance from execution plans.
- Added `GeneralFEMSolver.run_task(...)` and lightweight runtime bundle manifest export paths used by CLI and JobService.
- Fixed `JobService.plan_case(...)` backend routing import.

## Validation

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest tests -q
86 passed, 1 skipped
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.52
```

```text
PYTHONPATH=src python -B -m geoai_simkit demo --profile cpu-debug
case=pit-demo
backend=headless_stage_block_backend
stages=initial, wall_activation, excavate_level_1, excavate_level_2
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```

## Limitations

This environment validates CPU/headless contracts only. Desktop GUI launch and true GPU numerical execution still require optional PySide6/PyVista/Warp/CUDA dependencies and matching hardware.
