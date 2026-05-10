# Iteration 0.8.50 — GeoProject incremental solver and root GUI launcher

This iteration continues the GeoProjectDocument-native workflow and adds the first executable staged solver loop.

## Added runtime solver loop

- `geoai_simkit.geoproject.runtime_solver`
- Solid element assembly for Tet4 cells and preview Hex8 cells decomposed into linear tetrahedra
- Dense global stiffness assembly for dependency-light smoke verification
- Boundary condition application from compiled phase blocks
- Surface surcharge and self-weight load assembly
- Interface/contact candidates materialized as penalty spring elements
- Persistent cell state variables: strain, stress, plastic strain slot and internal flags
- Persistent interface state variables: normal gap, tangential slip, contact status and penalty forces
- Stage-wise incremental update using the previous phase displacement/state as history
- ResultStore back-writing for node displacement, settlement, cell stress, equivalent strain and interface fields
- Engineering metric curves regenerated from staged results

## Added GUI/service hooks

- `run_incremental_solver(document)` in `app.panels.solver_compiler`
- `VisualModelingSystem.run_incremental_solver()` facade method
- Compiled models now receive runtime `AssemblyBlock` and `IncrementalSolveBlock` diagnostics in metadata
- StateVariableBlock is populated with real cell/interface state tables after solving

## Added no-install root GUI launchers

Run from the repository root without installing the package:

```bash
python run_gui.py
```

Windows users can double-click:

```text
run_gui.bat
启动GUI.bat
```

macOS/Linux users can run:

```bash
./run_gui.sh
./run_gui.command
```

The launcher adds `src/` to `sys.path`, creates runtime folders, and starts the best available GUI stack. If PySide6 is unavailable, the fallback Tk/console workbench is used.

## Smoke check

```bash
PYTHONPATH=src python tools/run_geoproject_incremental_solver_smoke.py
```

Outputs:

- `reports/geoproject_incremental_solver_smoke.json`
- `exports/geoproject_incremental_solver_preview.geojson`

## Current boundary

The new solver is a lightweight engineering runtime. It is suitable for verifying the data path from GeoProjectDocument to assembly, staged solve and ResultStore back-write. It is not yet a commercial nonlinear geotechnical solver. The next hardening step should replace the dense smoke backend with sparse assembly, real interface integration, nonlinear constitutive return mapping and robust convergence control.
