# Iteration 0.8.56 - P0-P4 Completion and Modular Workflow Hardening

This iteration completes the P0-P4 modularisation pass by closing the remaining
contract, workflow, registry and boundary gaps left after v0.8.55.

## Completed scope

- Preserved caller-provided custom `ProjectReadPort`/`ProjectWritePort` objects
  at adapter boundaries instead of silently unwrapping them to legacy project
  documents.
- Added `ProjectPortCapabilities`, `is_project_port()` and
  `project_port_capabilities()` so modules can reason about read/write and
  transactional support without importing the concrete project implementation.
- Added workflow contracts:
  - `ProjectWorkflowRequest`
  - `WorkflowStepReport`
  - `ProjectWorkflowReport`
- Added `geoai_simkit.services.workflow_service.ProjectWorkflowService`, the
  canonical headless module-interoperability service for:
  `project_port -> meshing -> stage_planning -> fem_solver -> postprocessing`.
- Added thin GUI controller wrapper
  `geoai_simkit.app.controllers.workflow_controller` so GUI code can call the
  service without importing mesh/solver/result internals.
- Added plugin catalog validation through `validate_plugin_catalog()` and
  extended catalog smoke checks to verify descriptor, capability and health
  schemas across all registries.
- Added tests proving custom Project Ports are preserved, the canonical workflow
  can run through replaceable dummy plugins, workflow reports are serialisable,
  and the new workflow service/controller respect dependency boundaries.

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -B -m pytest tests -q
110 passed, 1 skipped
```

```text
PYTHONPATH=src python -B -m geoai_simkit --version
geoai-simkit 0.8.56
```

```text
PYTHONPATH=src python -B tools/run_core_fem_smoke.py
Core FEM smoke: 7/7 ok=True
```
