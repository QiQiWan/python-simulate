# v0.1.31 demo pit wall-interface completion

This iteration completes the missing demo workflow pieces so the parametric pit example is closer to a runnable retaining-wall excavation model.

## What changed

- Rebuilt the parametric pit mesh from a shared rectilinear mother grid so wall boundaries, pit boundaries, and excavation lift boundaries lie on the same coordinate breaks.
- Added automatic wall-soil node-pair interface generation for the demo pit. The demo now enables the wall in solver stages only when these interfaces were built successfully.
- Updated the default demo stages so wall activation follows the interface mode instead of staying permanently display-only.
- Strengthened pre-solve checks for wall stages:
  - display-only wall activation is blocked
  - missing outer/inner wall contact groups are reported explicitly
  - stage-specific wall interface coverage is checked
- Improved stage activation tree labels so the wall shows as `display-only` or `auto-interface`.
- Updated the script demo to use the same auto-interface workflow as the GUI demo.

## Remaining limitation

The demo wall still uses simplified node-pair interface springs, not a full surface-to-surface contact or mortar formulation. This is a pragmatic bridge so the example can run with the current solver architecture.
