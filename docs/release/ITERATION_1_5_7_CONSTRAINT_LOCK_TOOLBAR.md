# GeoAI SimKit 1.5.7 — Constraint Lock Toolbar

This iteration turns the existing along-edge and along-normal constraint projection into an explicit interaction workflow for continuous engineering placement.

## Added

- Persistent viewport constraint lock state in `SnapController`.
- Toolbar actions in the structure modeling panel:
  - Lock along edge
  - Lock along normal
  - Unlock constraint
- Right-click menu actions for active point / line / surface / block creation tools:
  - Lock along edge constraint
  - Lock along normal constraint
  - Unlock constraint
- Surface completion menu now includes constraint lock actions alongside finish / undo last point / cancel.
- Creation tools use a locked constraint for first clicks and following clicks, allowing continuous placement along one edge or one normal.
- Preview metadata now reports `constraint_locked` and `constraint_lock` so the viewport can render lock hints.
- PyVista preview overlay displays a lock label when a locked constraint is active.

## Intended workflow

1. Select or right-click a wall, beam, anchor, stratum boundary, excavation contour, face, or edge.
2. Choose `Lock along edge` or `Lock along normal` from the context menu or structure modeling toolbar.
3. Use point / line / surface / block tools continuously.
4. Created preview points are projected to the locked edge or locked normal until `Unlock constraint` is selected.

This supports repeated placement of wall points, beam lines, anchor endpoints, excavation contour points, and other CAD-FEM preprocessing geometry without re-selecting the same reference every time.

## Tests

- `tests/gui/test_iter157_constraint_lock_toolbar.py`
- Related regression group:
  - `test_iter153_structure_mouse_material_workflow.py`
  - `test_iter154_viewport_workplane_hover_creation.py`
  - `test_iter155_snap_crosshair_surface_menu.py`
  - `test_iter156_engineering_snap_constraints.py`
