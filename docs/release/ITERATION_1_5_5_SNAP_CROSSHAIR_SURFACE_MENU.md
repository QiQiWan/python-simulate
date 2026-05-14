# GeoAI SimKit 1.5.5 — Snap Crosshair Surface Menu

This iteration deepens the structure modeling mouse workflow by adding explicit visual feedback and error-reduction affordances for point, line, surface, and volume creation.

## Added

- Screen-space style cursor crosshair metadata for creation tools.
- Visible snap point overlay metadata for grid, endpoint, and midpoint snapping.
- Endpoint and midpoint snap hints in preview metadata.
- Surface creation right-click completion menu contract with finish, undo-last-point, and cancel actions.
- Structure panel snap-mode toggles for grid, endpoint, and midpoint snapping.
- PyVista adapter cursor overlay rendering for crosshair, snap glyph, and snap labels.
- Snap controller endpoint/midpoint candidates from curve/edge bounds and surface/face bounds.

## GUI workflow

1. Select a structure creation tool.
2. Move the mouse over the active workplane.
3. The viewport displays a crosshair and visible snap glyph.
4. Grid, endpoint, and midpoint snap modes display distinct snap labels.
5. Surface creation uses left-click to add points and right-click to open a completion menu.
6. The menu offers finish, undo last point, and cancel to reduce accidental face closure.

## Validation

- `tests/gui/test_iter155_snap_crosshair_surface_menu.py`
- `tests/gui/test_iter154_viewport_workplane_hover_creation.py`
- `tests/gui/test_iter153_structure_mouse_material_workflow.py`
