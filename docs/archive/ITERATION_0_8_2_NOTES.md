# GeoAI SimKit v0.8.2 / iter60 — nonlinear staged Tet4 solver closure

This iteration pushes the reference solver from a linear staged Tet4 path into a small but real nonlinear staged solve loop.

## Added

- `geoai_simkit.solver.nonlinear_tet4`
  - Picard-style nonlinear Tet4 stage solve.
  - Mohr-Coulomb material-state update path using the existing principal-space return mapping implementation.
  - Per-cell tangent refresh and nonlinear iteration diagnostics.
  - Contact active-set support for node-pair penalty contact using a normal-gap open/closed classifier.
- Tet4 linear operator extensions:
  - Custom per-cell tangent matrices.
  - Cell strain handoff for material-state update.
  - Contact active-set diagnostics.
- Stage backend integration:
  - Auto-enables nonlinear solving when Mohr-Coulomb materials are assigned, or when `settings.metadata["nonlinear"]["enabled"] = True`.
  - Exports `yield_flag`, `eq_plastic_strain`, and `yield_margin` result fields.
- Result package v8:
  - Adds `nonlinear_index.json`.
  - Adds GUI-ready `nonlinear_panel` payload.
- Foundation-pit Tet4 smoke case:
  - Soil regions now use Mohr-Coulomb parameters.
  - Nonlinear staged solve is enabled by default.

## Solver status

This is now a usable reference nonlinear solver for small staged Tet4 regression cases. It is still not a production-grade commercial geotechnical solver: it does not yet implement a full consistent global Newton tangent, advanced frictional interface elements, or HSS small-strain hardening. The implemented path is intended to stabilize the architecture and result contracts before moving the same contracts into a native/GPU backend.
