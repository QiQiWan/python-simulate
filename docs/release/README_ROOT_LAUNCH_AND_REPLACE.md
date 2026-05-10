# GeoAI SimKit v0.8.50 — Complete replacement package

This folder is intended to replace the previous project directory directly.

## Run the GUI without installing the package

From the project root:

```bash
python run_gui.py
python start_gui.py
python start_gui.py --smoke
```

`start_gui.py --smoke` validates the same GUI startup dependencies and workbench
payload path without entering the Qt event loop. Use it for automated checks on
headless or CI-style environments.

Windows:

```text
run_gui.bat
启动GUI.bat
```

macOS/Linux:

```bash
./run_gui.sh
./run_gui.command
```

The launcher uses `_no_install_bootstrap.py` to add `src/` to `sys.path`, so `pip install -e .` is not required.

## Verify the new GeoProject incremental solver

```bash
python tools/run_geoproject_incremental_solver_smoke.py
```

Expected outputs:

```text
reports/geoproject_incremental_solver_smoke.json
exports/geoproject_incremental_solver_preview.geojson
```

## What changed in v0.8.50

- Added executable GeoProjectDocument staged solver loop.
- Added solid element assembly for Tet4 and preview Hex8 cells.
- Added interface/contact penalty elements.
- Added persistent cell/interface state variables.
- Added stage-wise incremental solve and state propagation.
- Added ResultStore back-write for nodal, cell and interface fields.
- Added engineering metric curves from staged results.
- Added root GUI launchers for no-install startup.

## Current solver boundary

This is an executable engineering runtime for validating the complete data path. It is not yet a commercial nonlinear Plaxis-level solver. The next step is sparse assembly, stricter nonlinear return mapping, real interface integration, and convergence-controlled staged construction.
