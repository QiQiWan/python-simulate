# Iteration 0.9.0 Alpha - staged 3D phase workbench

This release advances the phase workbench from the P0-P5 architecture skeleton to a deterministic 0.9 Alpha demonstration workflow.

## Scope

- Adds a complete staged foundation-pit Alpha workflow.
- Adds project-level model validation gates.
- Adds a phase solver compiler service that wraps `GeoProjectDocument.compile_phase_models` with validation.
- Adds an Alpha system audit report for blockers, risks and readiness scoring.
- Adds a GUI-facing Alpha showcase panel payload.
- Exports a review bundle containing project JSON, validation, compiler payload, solver summary, result viewer JSON, audit JSON and legacy VTK.

## New modules

- `geoai_simkit.services.model_validation`
- `geoai_simkit.services.phase_solver_compiler`
- `geoai_simkit.services.system_audit`
- `geoai_simkit.examples.alpha_0_9_workflow`
- `geoai_simkit.app.panels.alpha_showcase`

## Alpha workflow

The workflow builds a compact PLAXIS-like staged construction case:

1. Initial soil mass with upper/lower soil volumes.
2. First excavation to -4 m.
3. First strut installation.
4. Second excavation to -8 m.
5. Second strut installation.

The case includes wall surfaces, struts, soil/structure/interface materials, phase activation snapshots, preview solid mesh, phase compiler payloads, incremental solver results and result exports.

## Validation gates

`validate_geoproject_model` checks:

- Solid volume existence and material assignment.
- Structure material and geometry references.
- Interface master/slave/material references.
- Phase snapshots and predecessor chains.
- Mesh cells/nodes/block tags/quality warnings.
- Result availability when requested.

## Audit result

`audit_geoproject_alpha` reports:

- Validation blockers.
- Mesh readiness and preview mesh risk.
- Phase compile/result count mismatch.
- Incremental solver convergence risks.

The Alpha demo can be considered workflow-ready when blocker count is zero. Preview mesh and non-converged phases remain explicit risks rather than hidden failures.

## Test command

```bash
PYTHONPATH=src pytest -q \
  tests/core/test_iter80_phase_workbench_and_viewport_runtime.py \
  tests/core/test_iter81_p0_p1_phase_shell_and_pyvista_adapter.py \
  tests/core/test_iter82_p2_p5_semantic_stl_stage_results.py \
  tests/workflow/test_iter90_alpha_0_9_workflow.py
```

Expected result in the development container:

```text
14 passed
```
