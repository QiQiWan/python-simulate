# Iteration v0.8.3 / iter61 — Stateful nonlinear staged solver

## What changed

This iteration strengthens the reference nonlinear Tet4 solver from a single-stage Picard prototype into a stateful staged solver.

Implemented:

- `solver/nonlinear_state.py` for serializing, restoring and summarizing committed material states.
- Stateful Mohr-Coulomb handoff between construction stages.
- Adaptive nonlinear load stepping and cutback controls in `NonlinearTet4Options`.
- New nonlinear solver contract: `nonlinear_tet4_stateful_cutback_mc_contact_v2`.
- Runtime persistence of `material_state_by_cell` and `material_state_summary`.
- Result package format `geoai-stage-result-package-v9`.
- New `material_state_index.json` and GUI `material_state_panel` payload.
- Tests for v9 material-state and nonlinear cutback metadata.

## Current solver scope

The solver is now suitable as a reference nonlinear staged solver for small Tet4 regression models:

- staged excavation activation/deactivation;
- K0 initial stress residual;
- equivalent excavation release loads;
- node-pair penalty contact with open/close diagnostics;
- Mohr-Coulomb state update;
- committed material-state transfer across stages;
- result package evidence chain for GUI inspection.

It is not yet a commercial-grade production solver. Missing pieces remain: consistent Newton tangent, strict frictional complementarity, robust automatic time stepping for large models, HSS/small-strain hardening state variables, and native GPU nonlinear assembly.
