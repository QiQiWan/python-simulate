# Iteration 0.8.19 — Modern software-shell polish

This iteration focuses on product-level polish around the existing PLAXIS-like modeling workflow.

## Added

- Modern workspace state contract with status bar, notification center, command palette, selection HUD, workflow timeline, solve readiness gate, autosave status, operation history, accessibility shortcuts and empty-state guidance.
- Project autosave/recovery helper that stores editable source-entity state only; meshes remain generated artifacts and are not treated as directly editable state.
- Operation history and geometry undo snapshot contracts for source-entity edits.
- Workbench and unified payload integration so modern UX state is available in scene and solve views.
- Solve presenter integration for the modern solve-readiness gate.

## Design principle

The GUI edits source entities, engineering components, BRep selections and bindings. Meshes are regenerated from entities and are never directly edited.
