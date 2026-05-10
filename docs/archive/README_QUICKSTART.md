# GeoAI SimKit v0.8.27-industrial-solver-core Quickstart

This package is designed to run from the source tree without installing the package itself.

## Run GUI without installing the current package

```bash
python run_gui_no_install.py
```

Windows:

```bat
run_gui_no_install.bat
```

macOS/Linux:

```bash
./run_gui_no_install.sh
```

GUI dependencies still need to exist in the Python environment:

```bash
python -m pip install -r requirements-gui.txt
```

## Run solver benchmarks

```bash
python run_solver_benchmarks.py
```

The benchmark report is written to:

```text
benchmark_reports/
```

Key outputs include:

```text
benchmark_report.md
benchmark_report.json
benchmark_report.csv
benchmark_gui_payload.json
material_paths/
material_reference/
material_calibration/
```

## New in v0.8.27

- Warp-native Hex8 kernelized nonlinear assembly benchmark entry.
- AMG / ILU / Krylov preconditioned sparse solver chain.
- MITC4-style plate/shell bending with local coordinates, reduced shear, drilling stabilization, and corotational diagnostics.
- Mortar-style wall-soil face search and augmented Lagrangian face integration benchmark.
- MC / HSS triaxial curve calibration with RMSE, MAE, R2 and SVG/CSV/JSON/Markdown export.

## Important engineering note

This is still a research and development finite-element platform.  The benchmark suite is designed to prevent silent over-claiming.  If GPU/Warp is not available, the GPU benchmark is reported as `capability_missing`; it is not counted as a real GPU solve.  The shell and mortar implementations are benchmark-grade and are not yet a full commercial finite-element kernel.
