# Iteration 0.8.4 / iter62 — solver acceptance and completion hardening

This iteration hardens the reference nonlinear staged Tet4 solver so solver outcomes are explicit instead of always reported as converged.

## Added

- `geoai_simkit.solver.convergence`
  - `SolverAcceptancePolicy`
  - `evaluate_stage_solver_acceptance()`
  - `summarize_solver_acceptance()`
- Stage-level solver acceptance rows stored in `model.metadata["solver_acceptance_rows"]`.
- `solver_acceptance_index.json` in stage result packages.
- GUI payload `solver_acceptance_panel`.
- CLI `result-package-info` now prints acceptance counts.

## Hardened

- Nonlinear solver contract upgraded to `nonlinear_tet4_stateful_cutback_mc_contact_v3`.
- `NonlinearTet4Options` now supports:
  - `strict_stage_acceptance`
  - `require_contact_active_set_stability`
  - `max_active_set_change`
  - stricter default for `accept_unconverged_final_step`.
- Nonlinear iterations now record `contact_active_set_change_count`.
- Backend stage status is now based on numerical acceptance:
  - `converged`
  - `accepted-with-warnings`
  - `failed`

## Result package

The package format is now `geoai-stage-result-package-v10`.
