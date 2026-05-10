# Iteration 0.8.1 / iter59 — Initial-stress residual handoff

This iteration pushes the geostatic workflow beyond diagnostic fields. The K0 geostatic stress state is now converted into a consistent Tet4 initial-stress residual contribution and assembled into the stage right-hand side.

## Main changes

- Added `element_initial_stress_force_tet4()` to compute `integral(B.T @ sigma0 dV)` for constant-stress Tet4 elements.
- Extended `solve_linear_tet4()` with `initial_stresses`, `initial_stress_factor`, and `initial_stress_mode`.
- The reference Tet4 backend now passes active-stage K0 stresses into the solver as an initial-stress residual.
- Added point results `initial_stress_residual` and `initial_stress_residual_magnitude`.
- Added `initial_stress_index.json` to the stage result package.
- Result package format updated to `geoai-stage-result-package-v7`.
- CLI `pit-tet4-smoke` and `result-package-info` now show initial-stress diagnostics.

## Current limitation

This is still a reference linear Tet4 implementation. It is a real RHS contribution, but not yet a full nonlinear geostatic initialization / excavation stress redistribution algorithm with plasticity and frictional contact iteration.
