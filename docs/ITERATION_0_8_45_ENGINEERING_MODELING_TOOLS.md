# Iteration 0.8.45 — Engineering Modeling Tools

This iteration upgrades the section editor into a more complete engineering modeling workbench.

## Added

- Grid and endpoint snap with viewport overlays.
- Interactive wall, strut and anchor axis creation.
- Horizontal soil-layer split driven by mouse drag/click.
- Excavation polygon split with deterministic section-prism partitioning.
- Contact/interface visual review with candidate rows, status, type and acceptance flow.
- Viewport primitives for support objects and contact/interface candidates.
- Object tree and property panel support for support structures and contact candidates.
- Smoke test: `tools/run_engineering_modeling_tools_smoke.py`.

## Notes

The excavation split uses a dependency-light section bounding-prism algorithm. It is stable and testable now; an OCC-backed boolean kernel can replace it later without changing the GUI contract.
