# Iteration 0.8.42 — system repair and GUI hardening

## Problem diagnosis

The v0.8.41 package had a coherent visual-modeling facade, but the delivered archive was incomplete and still depended on several legacy startup paths.

Key issues found:

1. `geoai_simkit._version` was missing, so package import could fail before GUI startup.
2. The archive missed canonical packages introduced by the visual modeling architecture: `document`, `commands`, `mesh`, `stage`, `results`, and the core `fem` API.
3. `VisualModelingSystem` imported commands that were not present in the archive: `GeneratePreviewMeshCommand` and `RunPreviewStageResultsCommand`.
4. The new Results tab expected `geoai_simkit.results.engineering_metrics`, but the module was missing.
5. The Tk fallback still built its payload through the old `WorkbenchService`, which could hang or fail when legacy project/model attributes diverged from the new engineering-document model.
6. The fallback window showed only Project / Workspace / Benchmark JSON, so when Qt/PyVista was unavailable the user could not inspect the visual-modeling state.
7. The PySide section viewport could display blocks, but viewport picking was not connected to the selection system.

## Fixes implemented

- Restored package metadata with `src/geoai_simkit/_version.py`.
- Restored missing canonical architecture packages from the previous architecture build:
  - `src/geoai_simkit/document`
  - `src/geoai_simkit/commands`
  - `src/geoai_simkit/mesh`
  - `src/geoai_simkit/stage`
  - `src/geoai_simkit/results`
  - `src/geoai_simkit/materials`
  - `src/geoai_simkit/pipeline`
  - `src/geoai_simkit/solver`
  - `src/geoai_simkit/fem`
- Added undoable mesh and preview-result commands:
  - `GeneratePreviewMeshCommand`
  - `RunPreviewStageResultsCommand`
- Added deterministic engineering metric result generation:
  - `build_preview_result_package()`
  - `result_summary()`
- Reworked `UnifiedWorkbenchController` so default fallback payloads are produced by `VisualModelingSystem`, not the old `WorkbenchService`.
- Extended the Tk fallback payload and tabs to include:
  - visual modeling payload
  - operation pages
  - benchmark panel
- Added viewport-click selection support in the PySide section viewport.

## Verified smoke checks

- `tools/run_visual_modeling_system_smoke.py`
- `tools/run_visual_modeling_architecture_smoke.py`
- `tools/run_block_pit_workflow_smoke.py`
- `tools/run_core_fem_smoke.py`

All generated report JSON files are available under `reports/`.

## Remaining limitations

This iteration hardens startup, packaging and GUI-data flow. It still uses a dependency-light section viewport and deterministic preview result backend. The next major step is to replace the preview backend with the real solver pipeline and to add true 3D picking, drag handles, right-click context menus, and editable geometry features.
