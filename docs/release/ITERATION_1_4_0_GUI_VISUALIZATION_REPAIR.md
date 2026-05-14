# Iteration 1.4.0 GUI Visualization and Interaction Repair

## Scope

This patch addresses the desktop symptoms reported after the strict dependency startup update:

- The visualization/modeling area could appear empty or text-only.
- Model visualization was not refreshed after loading a demo.
- Several toolbar/ribbon buttons gave no visible feedback.
- The PyVista workbench loaded the older foundation-pit case instead of the 1.4 multi-template GeoProject demo.
- Tests did not sufficiently verify renderable primitives and GUI action responsiveness.

## Fixes

### Lightweight model preview for PySide workbench

Added `geoai_simkit.app.viewport.visualization_diagnostics` and integrated it into `phase_workbench_qt.py`.

The PySide-only workbench now renders a lightweight 2D model preview using `QGraphicsView/QGraphicsScene`, backed by the same `ViewportState` primitive contract used by the PyVista path. This means the central model area is no longer a static text placeholder.

### Default demo preloading

The PySide workbench now attempts to preload the default 1.4 engineering demo so the visualization region has renderable model content immediately after startup.

### Button responsiveness

Phase-ribbon actions in the lightweight workbench now produce visible status/log updates. Validation, solve, mesh and export commands are routed to model diagnostics, full demo calculation, or bundle export where appropriate.

### PyVista demo loading repair

The NextGen PyVista workbench `Load Demo` button now loads the 1.4 GeoProject demo into the current workbench document via `set_geoproject_document`, refreshes `ViewportState`, rebinds the tool runtime and resets the viewport camera.

### Surface rendering repair

PyVista surface primitives now render as polygon faces with edges rather than as line-only data, making surfaces visible in the model viewport.

### Phase-command acknowledgement

Unimplemented or view/filter-like phase commands now explicitly log and update the status bar rather than appearing inert.

## Tests

Added:

- `tests/gui/test_gui_visualization_diagnostics_and_actions.py`

Validated:

- `tests/core`: 100 passed
- `tests/workflow`: 55 passed
- `tests/gui tests/visual_modeling`: 20 passed, 1 skipped
- `tests/architecture tests/runtime tests/solver`: 138 passed
- `compileall`: passed

The skipped GUI test is display-environment dependent.
