# GeoAI SimKit 1.5.4 — Viewport Workplane / Hover / Creation Feedback

This iteration deepens the structure mouse workflow introduced in 1.5.3.  The goal is to move the GUI from a collection of modeling buttons toward a predictable CAD-style interaction loop.

## Implemented

- Creation tools now emit explicit auto-selection metadata after point / line / surface / volume creation.
- Point creation now previews the point under the cursor before the first click.
- The PyVista viewport adapter now converts command results into a selection set so the newly created entity is selected immediately after refresh.
- Select / transform modes now render a hover overlay for pickable primitives.
- The structure panel now includes workplane controls for XZ / XY / YZ and a snap toggle.
- Right-clicking an existing entity selects it before opening the context menu, so material suggestions and promotion actions are aligned with the clicked object.
- The structure workflow payload is upgraded to `geoai_simkit_cad_structure_workflow_v3` and declares hover, cursor preview, workplane grid, snap toggle, right-click selection and created-entity auto-selection capabilities.

## User-facing effect

The expected modeling loop is now:

1. Pick a workplane.
2. Activate Create Point / Line / Surface / Volume.
3. Move the mouse and inspect preview feedback.
4. Left-click to create, or use right-click / Enter for surface completion.
5. The created entity becomes the active selection.
6. Right-click to promote it to soil, excavation, wall, interface, beam, anchor or pile.
7. Use the material recommendation to assign soil / concrete / steel / interface materials.

## Notes

The implementation remains headless-testable.  Native PySide6 + PyVistaQt interaction should be validated in the Windows `ifc` environment because full mouse event delivery depends on the Qt/VTK runtime.
