# GeoAI SimKit v0.8.25-nonlinear-global

This iteration continues the solver-hardening line from v0.8.24 and adds nonlinear global benchmarks plus GUI/result-package benchmark visibility.

## Added

- Hex8 nonlinear global solve benchmark with staged Newton-style tangent updates.
- Mohr-Coulomb triaxial p-q path export to CSV, JSON, Markdown, and SVG.
- Interface element active-set nonlinear loop for open/stick/slip contact states.
- Shell4 bending benchmark with rotational bending stiffness entering a 6-DOF/node global system.
- HSS/HSsmall unit-to-global nonlinear benchmark using Hex8 tangent updates and state propagation.
- Benchmark report integration with GUI payload and result package acceptance fragments.
- Root no-install benchmark runner remains available through `python run_solver_benchmarks.py`.

## Still limited

- Shell4 bending is a benchmark-grade bending regularization, not a full industrial shell formulation.
- Hex8 nonlinear solve is now global and iterative, but not yet a production large-strain nonlinear solver.
- Interface active set is a deterministic penalty/active-set implementation, not a full augmented-Lagrangian mortar contact solver.
- HSS/HSsmall validation is still research-grade and must not be described as PLAXIS-equivalent.
