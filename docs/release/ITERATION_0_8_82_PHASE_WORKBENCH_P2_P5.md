# Iteration 0.8.82 — Phase Workbench P2-P5

This iteration continues the PLAXIS-like phase workbench beyond P0/P1 and wires the remaining core workflow slices into testable services and GUI routes.

## P2 — Geometry semantic and material assignment

Added a semantic bridge from raw 3D geometry to engineering records:

- Volumes can be promoted to soil/geological/excavation/concrete semantic roles.
- Surfaces can be promoted to walls, plates, slabs, liners, or structural interfaces.
- Curves can be promoted to beams, struts, piles, embedded beams, or anchors.
- Materials can be assigned to volumes, structures, interfaces, and raw geometry entities.
- Semantic assignment is available through undoable commands and workbench service methods.

Key files:

- `src/geoai_simkit/geoproject/document.py`
- `src/geoai_simkit/commands/semantic_commands.py`
- `src/geoai_simkit/app/panels/semantic_assignment.py`
- `src/geoai_simkit/app/workbench.py`
- `src/geoai_simkit/app/workbench_window.py`

## P3 — STL import, repair, and volume-mesh pipeline

Added a headless import-wizard pipeline that can be wrapped by the GUI:

- Analyze ASCII/Binary STL quality through the existing STL loader.
- Classify import status: `surface_only`, `needs_repair`, `nonmanifold`, `closed_surface`, `solid_mesh_ready`.
- Run complex STL optimization/repair through the meshing module.
- Optionally generate a volume mesh, including the dependency-light `voxel_hex8_from_stl` path.
- Store import diagnostics and readiness payloads on the project/workbench document.

Key files:

- `src/geoai_simkit/services/stl_import_pipeline.py`
- `src/geoai_simkit/services/__init__.py`
- `src/geoai_simkit/app/workbench.py`
- `src/geoai_simkit/app/workbench_window.py`

## P4 — Stage configuration commands

Extended construction-stage editing with undoable phase commands:

- Add construction phases with optional predecessor or copy-from semantics.
- Activate/deactivate structures, interfaces, and loads per phase.
- Set phase water conditions and drawdown levels.
- Existing volume/block activation remains supported.

Key files:

- `src/geoai_simkit/commands/stage_commands.py`
- `src/geoai_simkit/commands/__init__.py`
- `src/geoai_simkit/geoproject/document.py`

## P5 — Result viewer and export shell

Added a result-viewer payload for the sixth phase:

- Build phase/metric/field/curve summaries from `GeoProjectDocument.ResultStore`.
- Generate deterministic preview results for phases.
- Export a conservative legacy ASCII VTK file with active-phase scalar tags.
- Route the GUI results tree and export action through the new payload.

Key files:

- `src/geoai_simkit/app/panels/result_viewer.py`
- `src/geoai_simkit/app/workbench.py`
- `src/geoai_simkit/app/workbench_window.py`

## Test coverage

New test file:

- `tests/core/test_iter82_p2_p5_semantic_stl_stage_results.py`

Regression command used:

```bash
PYTHONPATH=src pytest -q \
  tests/core/test_iter80_phase_workbench_and_viewport_runtime.py \
  tests/core/test_iter81_p0_p1_phase_shell_and_pyvista_adapter.py \
  tests/core/test_iter82_p2_p5_semantic_stl_stage_results.py \
  tests/visual_modeling/test_geoproject_document_framework.py \
  tests/visual_modeling/test_geometry_editor_smoke.py \
  tests/visual_modeling/test_mouse_geometry_interaction_smoke.py
```

Result:

```text
15 passed
```

GUI startup smoke command:

```bash
PYTHONPATH=src pytest -q tests/gui/test_start_gui_startup_smoke.py
```

Result:

```text
1 skipped
```

The skip is expected in the current headless environment when Qt GUI dependencies/display are unavailable.
