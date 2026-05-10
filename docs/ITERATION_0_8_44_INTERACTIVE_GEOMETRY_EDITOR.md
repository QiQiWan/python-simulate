# Iteration 0.8.44 — Interactive geometry editor

This iteration upgrades the modern geometry editor from coordinate-field creation
to true mouse-level interaction while preserving the dependency-light PySide-only
startup path.

## Implemented interaction contract

- Click-to-create point entities in the section viewport.
- Continuous line drawing: first click starts a line, every following click adds
  another connected segment until the user finishes/cancels the line tool.
- Surface sketching: repeated clicks add vertices; Enter, the close button, or a
  near-click on the first vertex closes the surface.
- Box block creation: two viewport clicks define an x-z rectangle and a thin y
  extrusion, producing a selectable block entity.
- Point dragging: selected point entities can be dragged and committed through
  the same command stack used by typed coordinate editing.
- Rubber-band selection: dragging in empty space selects points, edges, surfaces
  and blocks whose projected centers fall in the selection rectangle.
- Multi-selection: Ctrl toggles membership and Shift adds to the selection set.
- Right-click context menu: exposes clear selection, activate/deactivate selected
  blocks, hide/show selected blocks, assign a default manual material, delete
  selected geometry, switch tools and cancel pending drawing.

## New modules

- `geoai_simkit.app.geometry_mouse_interaction`
  - Display-backend-independent mouse interaction state machine.
  - Used by both GUI and headless smoke tests.
- `DeleteGeometryEntityCommand`
  - Undoable deletion for point, edge, surface, block and face entities.

## Updated modules

- `geoai_simkit.app.modern_qt_workbench`
  - Interactive QGraphicsView-based viewport.
  - Tool buttons now switch mouse modes instead of only running coordinate-input
    actions.
  - Coordinate-field creation is retained as a secondary precise-input path.
- `geoai_simkit.app.visual_modeling_system`
  - Stable multi-selection helpers.
  - Batch visibility and stage activation commands for selected blocks.
  - Deletion entry point for selected geometry entities.
- `geoai_simkit.commands`
  - Exports the new geometry deletion command.

## Validation

Run:

```bash
PYTHONPATH=src python tools/run_mouse_geometry_interaction_smoke.py
```

Expected report:

```text
reports/mouse_geometry_interaction_smoke.json
```

The smoke covers point creation, continuous line creation, surface closure, block
creation, point dragging, add-selection, box-selection, right-click action
contract, visibility actions and stage activation actions.
