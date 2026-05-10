# Iteration 0.8.43 — Modern geometry editor

This iteration turns the visual-modeling workbench from a block-only preview into a dependency-light geometry editor foundation.

## Added

- Stable geometry entities:
  - `PointEntity`
  - `EdgeEntity`
  - `SurfaceEntity`
  - `BlockEntity`
- `GeometryEditor` service for coordinate locating, grid snapping, point creation, line creation, surface creation, block creation and point movement.
- Undoable commands:
  - `CreatePointCommand`
  - `MovePointCommand`
  - `CreateLineCommand`
  - `CreateSurfaceCommand`
  - `CreateBlockCommand`
- Interactive tool skeletons:
  - `PointTool`
  - `LineTool`
  - `SurfaceTool`
  - `BoxBlockTool`
- Viewport primitives for point / edge / surface / block display and stable picking.
- Object-tree and property-panel support for points, lines/edges and surfaces.
- PySide-only workbench coordinate input strip for point, line, surface, block and selected-point movement.
- Smoke test: `tools/run_geometry_editor_smoke.py`.

## Current scope

The editor is intentionally dependency-light. It does not replace OCC CAD operations yet. It establishes the engineering-object editing contract required for PLAXIS/Abaqus-style modeling: stable IDs, selection, commands, undo/redo, viewport primitives and downstream mesh/result invalidation.
