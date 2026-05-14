# Iteration 1.0.5 Basic

## Scope

This iteration hardens the 1.0.0-basic foundation-pit workflow into a 1.0.5-basic release line.

Implemented increments:

- **1.0.1 GUI desktop hardening**: headless-safe GUI contract audit for the six-phase workbench, ribbon action routing and optional desktop runtime availability.
- **1.0.2 Gmsh/OCC production meshing route**: Gmsh/OCC-preferred meshing route with explicit audited shared-node Hex8 fallback in environments without a full Gmsh/OCC desktop runtime.
- **1.0.3 K0/self-weight initialization**: deterministic K0 initial stress field from material unit weights, cell centroids and friction-angle-derived K0.
- **1.0.4 Staged Mohr-Coulomb controls**: versioned staged Mohr-Coulomb control block attached to phase settings and material metadata.
- **1.0.5 reporting/tutorial**: review bundle, Markdown/JSON report, VTK export and tutorial artifact.

## Main entry points

- `geoai_simkit.examples.release_1_0_5_workflow.build_release_1_0_5_project`
- `geoai_simkit.examples.release_1_0_5_workflow.run_release_1_0_5_workflow`
- `geoai_simkit.services.release_acceptance_105.audit_release_1_0_5`
- `geoai_simkit.app.panels.release_105_showcase.build_release_1_0_5_showcase_payload`

## Review bundle

Generated under:

```text
/docs/release/release_1_0_5_review_bundle/
```

Key artifacts:

- `release_1_0_5_project.geoproject.json`
- `release_1_0_5_acceptance.json`
- `release_1_0_5_gui_hardening.json`
- `release_1_0_5_mesh_route.json`
- `release_1_0_5_k0_initial_stress.json`
- `release_1_0_5_mohr_coulomb_control.json`
- `release_1_0_5_engineering_report.md`
- `release_1_0_5_tutorial.md`
- `release_1_0_5_results.vtk`

## Acceptance status

Current review bundle status:

```text
accepted_1_0_5_basic
blockers: 0
warnings: 3
```

Warnings are environmental or explicitly bounded:

1. PySide6 is not installed in the CI/headless environment.
2. PyVista is not installed in the CI/headless environment.
3. Gmsh/OCC route fell back to the audited shared-node Hex8 production mesh.

## Tests

```bash
PYTHONPATH=src:. pytest -q
PYTHONPATH=src python -m compileall -q src tests
```

Observed result:

```text
282 passed, 1 skipped
compileall passed
```

## Boundary

This is still `1.0.5-basic`, not a certification-grade commercial geotechnical solver.  It has a hardened workflow, K0 field, staged Mohr-Coulomb controls and release-gated reporting, while the global solve remains the lightweight compact staged kernel.  Production-grade Gmsh/OCC tetrahedral meshing and a full global nonlinear Mohr-Coulomb Newton solver remain next-line work.
