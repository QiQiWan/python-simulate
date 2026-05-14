# Iteration 1.4.6 — CAD Workbench Stabilization

## Problem analysis

The 1.4.5 workbench had enough backend contracts for CAD/OCC, STEP/IFC, topology binding and native-certification gates, but the desktop CAD experience was still weak. The main functional gaps were:

- Tool activation and phase switching could repopulate panels and trigger viewport rebuilds, which made the 3D model flicker.
- The workbench mixed demo-run actions with the in-memory edited project; running calculations could reload a template and make user-created geometry appear to be lost.
- The UI used a large header, card strip and embedded splitter layout. It consumed too much vertical space and did not feel like a modern CAD shell.
- Toolbars were placed inside regular layouts, so they could not float/dock like CAD tool palettes.
- Browser, inspector and console panels were not QDockWidget-based; users could not float or rearrange them.
- Requirements were split across multiple files, while startup preflight did not check every dependency that the GUI/native-CAD stack now relies on.

## Changes

### GUI layout

The PySide/PyVista phase workbench was rebuilt as a compact CAD-style shell:

- Compact top navigation toolbar for the six stages.
- Graphical contextual phase ribbon on top.
- Graphical CAD modeling toolbar on top.
- Toolbars are movable and floatable, except the primary phase navigation bar.
- Model browser, inspector and console are QDockWidget panels and can float/dock.
- The large header/card layout has been removed from the main shell.

### Interaction state

- Tool activation no longer repopulates the full UI or clears the 3D viewport.
- Phase switching updates toolbar/panel content without resetting the model.
- The scene now uses a dirty-revision policy. It renders on explicit geometry/project changes, not on every phase/tool operation.
- Demo calculations run externally and do not replace the in-memory edited project by default.

### Dependency management

- All requirements have been consolidated into `requirements.txt`.
- Removed split requirement files such as `requirements-gui.txt`, `requirements-meshing.txt`, `requirements-cad-facade.txt` and `requirements-step-ifc.txt`.
- Startup preflight now checks all main runtime dependencies from the unified stack, including GUI, 3D, meshing, CAD, IFC, reporting and verification dependencies.

### Version

Internal version:

```text
1.4.6-cad-workbench-stabilization
```

Package version in `pyproject.toml`:

```text
1.4.6
```

## Remaining CAD gaps

This release improves usability and startup correctness, but the CAD stack still needs further work:

- Direct face/edge picking in PyVista should be made cell-aware, not just actor/entity-aware.
- Drag handles should evolve from simple selection handles to axis gizmos with numeric delta feedback.
- The native OCC BRep-certified path still requires verification in a desktop environment with OCP/pythonocc/IfcOpenShell installed.
- STEP/IFC exact curved-face persistent naming needs real model benchmark files.
- Boolean face lineage still has derived and contract paths; native OCC history maps should be integrated when available.

## Test summary

Validated groups:

- `tests/core tests/workflow tests/gui/test_iter146_cad_workbench_stabilization.py`: 160 passed
- CAD/GUI selected regression: 24 passed
- `tests/architecture tests/runtime tests/solver`: 138 passed
- `tests/visual_modeling tests/gui/test_start_gui_startup_smoke.py`: 10 passed, 1 skipped
- `compileall`: passed
