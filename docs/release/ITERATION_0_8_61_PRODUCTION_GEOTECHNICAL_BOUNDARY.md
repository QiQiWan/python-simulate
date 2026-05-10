# Iteration 0.8.61 - Production Geotechnical Solver Boundary and GUI Slimming

## Purpose

Move the 3D geotechnical pipeline from feature-preview wiring toward a production-facing boundary: typed readiness DTOs, GUI-free readiness service, nonlinear staged control diagnostics and Qt-free controllers for new GUI actions.

## Added

- `geoai_simkit.contracts.geotechnical` with strict DTOs for solid mesh, material mapping, boundary conditions, loads, interfaces, stage activation and analysis readiness.
- `geoai_simkit.services.geotechnical_readiness.build_geotechnical_readiness_report`.
- `geoai_simkit.solver.nonlinear_boundary` with `NonlinearRunControl`, increment/iteration records and `run_staged_mohr_coulomb_boundary`.
- `staged_mohr_coulomb_cpu` solver backend.
- Qt-free GUI controllers for material mapping, boundary/load summary and geotechnical staged workflows.

## Validation

```text
143 passed, 1 skipped
Core FEM smoke: 7/7 ok=True
geoai-simkit 0.8.61
```

## Scope note

This version establishes the production solver boundary and diagnostics. The global tangent still reuses the current linear solid assembly, so full consistent-tangent Newton return mapping and production active-set contact remain follow-on solver-core work.
