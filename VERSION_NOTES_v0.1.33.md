# GeoAI SimKit v0.1.33

## This release

This release continues the staged excavation demo upgrade toward a more PLAXIS-like workflow.

### Highlights
- Added backward-compatible `SimulationModel.object_record_for_key()` alias to stop GUI demo crashes in mixed-version code paths.
- Upgraded demo coupling from plain wall interface mode to a **PLAXIS-like auto mode**:
  - automatic wall-soil node-pair interfaces
  - automatic crown beam generation
  - automatic level-1 and level-2 strut generation
- Improved parametric pit meshing anchors so the demo mesh includes:
  - pit center lines
  - quarter-depth strut levels
  - better-aligned support node locations
- Extended pre-solve diagnostics to verify expected support groups by stage when running in plaxis-like auto mode.
- Updated GUI demo creation flow and status messaging to report automatic interface/support generation.

## Expected demo behavior
- `initial`: wall active with wall-soil interfaces and crown beam
- `excavate_level_1`: wall active with crown beam + level 1 struts
- `excavate_level_2`: wall active with crown beam + level 1 + level 2 struts

## Notes
- The current coupling is still based on node-pair interfaces plus frame/truss structural elements.
- It is a practical staged-coupling workflow, not a full general 3D nonmatching surface-to-surface contact implementation.
