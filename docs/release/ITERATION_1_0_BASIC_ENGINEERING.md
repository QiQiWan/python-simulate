# Iteration 1.0.0 Basic Engineering Release

## Scope

This iteration promotes the 0.9 Alpha staged foundation-pit workflow into a baseline 1.0 engineering workflow.  The release focuses on a stable end-to-end path rather than broad feature expansion.

## Delivered capabilities

- Production-marked shared-node Hex8 mesh generation for axis-aligned GeoProject volumes.
- Compact active-node phase compilation to remove inactive/orphan DOFs from staged solver input.
- Strict 1.0 release acceptance audit for mesh, validation, compiler, solver convergence and results completeness.
- Structured engineering report export in Markdown and JSON.
- GUI-facing 1.0 showcase payload for the release workflow.
- Full save/load regression for the accepted staged project.

## Important engineering boundary

The built-in 1.0 demo is accepted as a surcharge-only linear-static staged verification case.  Self-weight is explicitly disabled for this baseline case and recorded in project metadata.  Certification-grade studies still require validated Gmsh/OCC meshing, calibrated constitutive models and domain-specific engineering review.

## Acceptance result

The generated review bundle is stored in `docs/release/release_1_0_review_bundle/` and contains:

- `release_1_0_project.geoproject.json`
- `release_1_0_validation.json`
- `release_1_0_compiler.json`
- `release_1_0_solver_summary.json`
- `release_1_0_acceptance.json`
- `release_1_0_result_viewer.json`
- `release_1_0_result_summary_export.json`
- `release_1_0_results.vtk`
- `release_1_0_engineering_report.md`
- `release_1_0_engineering_report.json`

## Regression status

`PYTHONPATH=src:. pytest -q`

Result: `277 passed, 1 skipped`.

The skipped test is GUI-display-environment dependent and was already expected in previous iterations.
