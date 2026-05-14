# Iteration 1.4.1 — Geometry Authoring Enhancement

## Scope

This iteration closes the main usability gaps in the interactive geometry modeling loop:

- drag-based edit handles for selected point/curve/surface/volume entities;
- numeric coordinate and dimension entry from the property panel;
- Shift/Ctrl multi-selection, box-selection contract and inverse selection;
- Move, Copy, Rotate, Scale transform tools;
- surface extrusion, axis-plane volume cutting and deferred boolean feature records;
- direct semantic/material assignment from the right-side property panel;
- desktop interaction recording contract for manual/automated GUI regression.

## Implementation highlights

### New command layer

`geoai_simkit.commands.interactive_geometry_commands` adds undoable GeoProjectDocument-native commands:

- `TransformGeometryCommand`
- `CopyGeometryCommand`
- `SetEntityCoordinatesCommand`
- `ExtrudeSurfaceCommand`
- `CutVolumeCommand`
- `BooleanGeometryCommand`

The commands are designed for GUI robustness: they use document snapshots for undo and mutate raw geometry through the command stack.

### New interaction tools

`geoai_simkit.app.tools.geometry_edit_tools` adds runtime tools:

- `drag_move` / `move`
- `copy`
- `rotate`
- `scale`
- `extrude`
- `cut`
- `boolean` / `boolean_subtract`

These are registered by `default_geometry_tool_runtime()` alongside the existing select/point/line/surface/block tools.

### Selection controller

`geoai_simkit.app.viewport.selection_controller` adds Qt-free multi-selection semantics:

- replace selection;
- Shift/add selection;
- Ctrl/toggle selection;
- box selection by 3D bounds;
- inverse selection.

### Viewport adapter

`PyVistaViewportAdapter` now supports:

- mouse release events for drag tools;
- Qt keyboard modifier detection;
- selection overlays plus edit handles;
- handle actor mapping back to entities.

### Workbench UI

`phase_workbench_qt.py` now exposes:

- modeling toolbar buttons for Move, Copy, Rotate, Scale, Extrude, Cut, Union, Subtract and Invert;
- a right-side `语义/坐标` panel for entity ID/type, x/y/z, dimensions, semantic type and material;
- command-stack-backed coordinate and semantic/material actions.

### Desktop recording contract

`geoai_simkit.services.desktop_interaction_recording` defines the desktop regression script for:

- loading a template;
- creating geometry;
- selecting and dragging handles;
- numeric editing;
- semantic assignment;
- running/exporting the complete calculation.

## Tests

Added:

- `tests/gui/test_iter141_geometry_authoring_enhancements.py`

Validated:

- new 1.4.1 authoring tests: `5 passed`;
- existing geometry interaction repair tests: `5 passed`;
- P0/P1 runtime tests: `4 passed`;
- selected workflow regressions: `20 passed`;
- core phase/semantic workflow tests: `11 passed`;
- `compileall`: passed.

## Remaining limitations

- Boolean union/subtract is recorded as an auditable deferred feature; native OCC execution should consume this feature in a later meshing/geometry-kernel iteration.
- Box selection is exposed as a controller contract and can be wired to a screen-drag rectangle in a later desktop recording iteration.
- Rotate currently provides a stable Z-axis rotation command; arbitrary-axis rotate gizmos can be added later.
