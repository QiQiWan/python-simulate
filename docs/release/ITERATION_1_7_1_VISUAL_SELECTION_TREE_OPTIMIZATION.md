# Iteration 1.7.1 - Visual selection and compact model tree optimization

## Scope

This patch addresses the imported geology visualization artifact, viewport-to-tree selection synchronization, and the model browser complexity.

## Changes

1. Imported mesh visualization no longer draws a coincident full-surface wireframe on top of the colored geology surface. The imported model is rendered as a solid categorical surface with feature edges and outline only, with lighting disabled on the main actor to reduce moire, ghost-shadow and flower-shadow artifacts.
2. Imported geology mesh actors now carry stable `geoai_*` cell metadata, including entity id, kind, source entity id and layer value. Picking an imported mesh cell selects the corresponding `geology_layer:<value>` entity.
3. Selection overlays now support imported geology models and imported geology layers even when they are not represented by regular geometry primitives. The overlay falls back to mesh or layer bounds and displays an edit handle.
4. The Qt workbench model browser now uses a compact engineering tree. It exposes only: 地质体、围护墙、水平支撑、梁、锚杆. The original full tree builder is retained for diagnostics and tests.
5. Viewport selection now synchronizes back to the left model tree. Imported geology layer picks resolve to the matching `geology_layer:<value>` node; structure and geometry selections resolve through entity id/source id aliases.

## Files changed

- `src/geoai_simkit/app/viewport/pyvista_adapter.py`
- `src/geoai_simkit/app/panels/object_tree.py`
- `src/geoai_simkit/app/shell/phase_workbench_qt.py`

## Validation

- Python compile check passed for the modified modules.
- Targeted smoke run passed 6 tests and hit one pre-existing contract mismatch in `tests/gui/test_gui_visualization_diagnostics_and_actions.py`, where the test expects `phase_workbench_qt_payload_v1` while current code returns `phase_workbench_qt_payload_v2`.
