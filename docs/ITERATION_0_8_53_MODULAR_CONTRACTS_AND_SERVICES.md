# Iteration 0.8.53 - Modular Contracts and Service Boundary Hardening

## Goal

Advance P0/P1 modularization so core subsystems can be separated, optimized and replaced through stable interfaces instead of direct implementation coupling.

## P0 - stable interface contracts

Added `geoai_simkit.contracts` as a dependency-light package. It defines request/result DTOs and protocols for:

- `project`: `ProjectContext`, `ProjectSnapshot`, `ProjectMutation`, `ProjectTransaction`, read/write/repository ports.
- `geology`: geology source/importer contracts.
- `geometry`: geometry build request/result contracts.
- `mesh`: `MeshRequest`, `MeshResult`, `MeshGenerator`, `MeshGeneratorRegistry`.
- `stage`: `StageCompileRequest`, `StageCompileResult`, `StageCompiler`.
- `solver`: `SolveRequest`, `SolveResult`, `SolverCapabilities`, `SolverBackend`, `SolverBackendRegistry`.
- `runtime`: runtime compile and bundle-store contracts.
- `results`: result request/summary/sink/postprocessor contracts.

The contracts package deliberately avoids imports from GUI, solver implementation, pipeline, mesh implementation, PySide6, PyVista and Warp.

## P1 - module interoperability chain

The primary module chain is now explicit:

```text
geology_import -> document_model -> meshing -> stage_planning -> fem_solver -> postprocessing
```

Implemented changes:

- Added `geoai_simkit.modules.meshing` facade.
- Added `geoai_simkit.modules.stage_planning` facade.
- Updated module registry to include `meshing` and `stage_planning` as first-class update targets.
- Updated `geoai_simkit.modules.fem_solver` to expose `solve_project()` and resolve solver backends through `SolverBackendRegistry`.
- Preserved `run_project_incremental_solve()` as a backward-compatible summary-returning entrypoint.
- Added adapters for existing implementations instead of moving implementation code aggressively.

## Adapters

Added `geoai_simkit.adapters`:

- `geoproject_adapter.py`: turns a `GeoProjectDocument` into a `ProjectContext` and snapshot/mutation boundary.
- `mesh_adapters.py`: wraps current layered and tagged-preview meshers as `MeshGenerator` implementations.
- `legacy_solver_adapter.py`: wraps the current GeoProject incremental runtime solver as the `reference_cpu` `SolverBackend`.

## Services

Added `geoai_simkit.services` for headless orchestration:

- `services.job_service`
- `services.blueprint_progress`
- `services.system_readiness`

Old imports under `geoai_simkit.app.*` are retained as compatibility shims.

## Architecture tests

Added `tests/architecture/test_import_boundaries.py` to prevent regressions:

- `contracts` must remain dependency-light.
- `services` must not import GUI/rendering/GPU frameworks directly.
- `solver` and `mesh` must not import the app layer.

## Root layout cleanup

Root was reduced to essential files. Duplicate launchers and release-specific documents were moved to:

- `tools/launchers/`
- `docs/release/`
- `docs/archive/`

## Validation

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest tests -q
92 passed, 1 skipped
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.53
```
