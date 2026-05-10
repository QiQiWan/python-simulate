# Iteration 0.7.6 / iter54 - Interface-ready contact solving

This iteration moves the pit Tet4 smoke workflow from a contact-report pipeline to an interface-ready contact-solver pipeline.

## Key changes

- Added headless interface-ready mesh rebuilding for PyVista-like grids.
  - `pipeline.interface_ready` no longer requires PyVista for the lightweight Tet4 regression grid.
  - The node split path supports `Grid(points, cells)` style meshes used by CLI/CI demos.
- Improved node-pair interface remapping after node split.
  - Interface point ids are remapped by declared slave/master regions, not only by one duplicate side.
  - This fixes the previous all-`missing_pair` contact assembly issue in stage solves.
- Pruned degenerate same-id contact pairs.
  - Coincident but distinct ids are retained as valid zero-gap penalty-contact pairs.
  - Exact same-id self-pairs are removed and recorded in diagnostics.
- Treated same-region block seams as continuity/tie rows.
  - Internal wall-wall or soil-soil seams inside a single solver region no longer generate artificial contact constraints.
- Upgraded the foundation-pit Tet4 smoke case.
  - The model now applies interface-ready node split before stage solving.
  - The initial stage produces nonzero effective contact pairs with zero zero-length pairs.

## Expected pit smoke diagnostics

Typical `pit-tet4-smoke` contact diagnostics after this iteration:

```text
point_count: 128
interface_count: 16
total_node_pair_count: 80
effective_pair_count at initial stage: 80
zero_length_pair_count at initial stage: 0
remaining_split_plans: 0
```

During excavation stages, some pairs become `missing` because the excavated region is no longer active in the stage submesh. This is expected for the current active-submesh reference backend.

## Still not production-grade

- Penalty contact is still a linear reference implementation.
- There is no nonlinear opening/closing or frictional stick-slip update yet.
- Release boundaries are still stage metadata rather than full geostatic stress-release elements.
- The GUI result panel still needs direct `gui_index.json` consumption.

## Recommended next step

Connect interface-ready contact definitions to a GUI-visible contact diagnostics panel and implement stage-aware deactivation of contact rows so excavated-region pairs are explicitly marked inactive instead of merely missing from the active submesh.
