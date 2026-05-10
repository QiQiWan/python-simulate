# Iteration v0.8.5 / iter63 — nonlinear material-residual solver hardening

## What changed

This iteration hardens the reference staged nonlinear Tet4 solver by adding a true material-stress residual evaluation:

- `assemble_internal_force_tet4()` assembles `integral(B^T sigma dV)` from the updated material stress state.
- `summarize_material_residual()` reports the nonlinear material residual norm, RHS norm, free-DOF residual norm and residual ratio.
- `solve_nonlinear_tet4_stage()` now uses the material residual ratio as an optional convergence gate.
- The backend exports `nonlinear_material_residual`, `nonlinear_material_residual_magnitude` and `nonlinear_internal_force` result fields.
- The stage-result package is upgraded to `geoai-stage-result-package-v11` with `nonlinear_material_residual_index.json`.
- The solver acceptance policy is upgraded to `solver_acceptance_policy_v2` and warns on high material residuals.

## Why this matters

v0.8.4 could run nonlinear staged analyses, but the convergence evidence still leaned on the tangent linear-system residual.  v0.8.5 evaluates the residual from the actual updated material stress state, which is closer to the equilibrium check expected from a nonlinear finite-element solver.

## Still not commercial-grade

The solver is still a compact reference implementation.  It does not yet provide a full consistent Newton tangent, strict frictional contact complementarity, HSS small-strain state variables, or GPU-native nonlinear assembly.
