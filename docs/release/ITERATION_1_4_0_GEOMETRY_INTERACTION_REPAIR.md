# Iteration 1.4.0 — Geometry Interaction Modeling Repair

## Problems found

1. The PySide six-phase workbench embedded a 3D PyVista view, but it did not bind `ViewportToolRuntime`, `CommandStack`, or viewport mouse/key observers. As a result, ribbon tools could be activated visually, but clicking in the model did not create point/line/surface/block geometry.
2. Picking relied on stale plotter picker state and weak actor identity mapping. Selection could fail even when the actor was visibly clicked.
3. There was no shared snapping service. Mouse-created geometry could be imprecise and hard to connect to existing model vertices.
4. Surface creation did not support removing the last point. Right-click did not finish a polygon.
5. The PySide workbench had no work-plane or snap controls. Users could not reliably choose XZ/XY/YZ modeling planes.
6. Undo/redo existed in the backend command stack, but was not exposed in the phase workbench modeling controls.

## Fixes implemented

- Added `app.viewport.snap_controller.SnapController` with grid, endpoint and midpoint snapping.
- Bound `CommandStack`, `ViewportState`, `default_geometry_tool_runtime`, and `PyVistaViewportAdapter` in the PySide phase workbench.
- Bound PyVista mouse/key events in the PySide phase workbench.
- Added work-plane controls: XZ, XY, YZ.
- Added snap on/off control.
- Added Undo/Redo controls for interactive geometry commands.
- Improved PyVista picking with `vtkPropPicker` at the current screen coordinate.
- Improved actor-to-entity mapping using multiple actor keys and optional actor metadata.
- Added selection overlay rendering.
- Added surface Backspace/Delete behavior and right-click commit.
- Added line/box Backspace/Delete cancel behavior.
- Added geometry interaction contract to the Qt payload.

## Verification

Targeted tests:

```bash
PYTHONPATH=src:. pytest -q tests/gui/test_geometry_interaction_modeling_repair.py
PYTHONPATH=src:. pytest -q tests/core/test_iter81_p0_p1_phase_shell_and_pyvista_adapter.py
PYTHONPATH=src:. pytest -q tests/gui/test_gui_thread_safety_and_3d_viewport_contract.py tests/gui/test_gui_visualization_diagnostics_and_actions.py tests/gui/test_gui_runtime_interruption_and_legacy_cleanup.py
PYTHONPATH=src:. pytest -q tests/workflow/test_iter140_release_1_4_0_multi_template_workflow.py
PYTHONPATH=src python -m compileall -q src tests
```

Results from this repair pass:

- geometry interaction repair tests: 5 passed
- P0/P1 viewport runtime tests: 4 passed
- GUI stability/visualization tests: 8 passed
- 1.4 workflow tests: 7 passed
- compileall: passed

## Remaining usability gaps

This pass restores the core creation/selection loop. Remaining work for a production-grade CAD-like geometry editor:

1. Drag-move editing with handles.
2. Numeric coordinate entry and dimension constraints.
3. Multi-select with Shift/Ctrl and transform operations.
4. Boolean/split operations for non-axis-aligned solids.
5. Persistent semantic assignment directly from the selection inspector.
6. Full visual highlight styles per phase and entity type.
7. Recorded GUI interaction tests on a real desktop display.
